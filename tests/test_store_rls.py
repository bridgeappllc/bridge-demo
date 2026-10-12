"""DB rule tests for store requirements: delete my account + reports (same harness as test_social_rls.py)."""
import json, os, uuid, psycopg
DSN = os.environ.get("DSN", "postgresql://postgres@127.0.0.1:54322/postgres")
conn = psycopg.connect(DSN, autocommit=True)
passed = failed = 0
def new_user(name):
    uid = str(uuid.uuid4())
    conn.execute("insert into auth.users (id, instance_id, aud, role, is_anonymous, created_at, updated_at) values (%s, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', true, now(), now())", (uid,))
    if name: run(uid, "insert into profiles (id, display_name) values (%s, %s)", (uid, name))
    return uid
def run(uid, sql, params=()):
    with conn.transaction():
        with conn.cursor() as cur:
            if uid is None:
                cur.execute("set local role anon"); cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": "anon"}),))
            else:
                cur.execute("set local role authenticated"); cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": uid, "role": "authenticated"}),))
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else cur.rowcount
def check(name, cond):
    global passed, failed
    if cond: passed += 1; print("  PASS", name)
    else: failed += 1; print("  FAIL", name)
def denied(name, uid, sql, params=()):
    try:
        r = run(uid, sql, params); ok = (r == 0 or r == [] or r == [(None,)])
        check(f"{name} (filtered: {r})" if ok else f"{name} -> unexpectedly allowed: {r}", ok)
    except psycopg.Error as e: check(f"{name} (error: {str(e).splitlines()[0][:70]})", True)
def raises(name, uid, sql, params=(), like=""):
    try: r = run(uid, sql, params); check(f"{name} -> unexpectedly ok: {r}", False)
    except psycopg.Error as e: check(f"{name} (error: {str(e).splitlines()[0][:70]})", like.lower() in str(e).lower())

tag = uuid.uuid4().hex[:6]
A, B, C, D, E = (new_user(n) for n in (f"Alice{tag}", f"Bob{tag}", f"Carol{tag}", f"Dave{tag}", f"Eve{tag}"))
adm = lambda sql, p=(): conn.execute(sql, p).fetchall()
def mkbridge(owner, name, title):
    r = run(owner, "select id, invite_token from create_bridge(%s,%s,%s)", (name, title, f"https://example.org/{title}-{tag}"))[0]
    return str(r[0]), r[1]
def answer(uid, b): run(uid, "insert into answers (bridge_id,user_id,a1,a2,a3) values (%s,%s,'x','y','z')", (b, uid))
def say(uid, b, t): run(uid, "insert into messages (bridge_id,user_id,body) values (%s,%s,%s)", (b, uid, t))
def befriend(x, y): run(x, "select send_friend_request(%s)", (y,)); run(y, "select respond_friend_request(%s,true)", (x,))

# --- setup
befriend(A, B); befriend(C, D)
run(A, "select block_user(%s)", (D,))
for i in (1, 2): run(A, "insert into library_items (user_id,url,title) values (%s,%s,%s)", (A, f"https://example.org/a{i}-{tag}", f"A item {i}"))
run(B, "insert into library_items (user_id,url,title) values (%s,%s,'B item')", (B, f"https://example.org/b-{tag}"))
b1, t1 = mkbridge(A, f"Alice{tag}", "shared1")           # A owner + B
run(B, "select join_bridge(%s,%s)", (t1, f"Bob{tag}")); answer(A, b1); answer(B, b1); say(A, b1, "from A"); say(B, b1, "from B")
b2, t2 = mkbridge(A, f"Alice{tag}", "solo")              # only A
b3, t3 = mkbridge(C, f"Carol{tag}", "shared3")           # C owner + A
run(A, "select join_bridge(%s,%s)", (t3, f"Alice{tag}")); answer(C, b3); answer(A, b3); say(C, b3, "from C"); say(A, b3, "A in b3")
b4, t4 = mkbridge(B, f"Bob{tag}", "others")              # B + C, A not involved
run(C, "select join_bridge(%s,%s)", (t4, f"Carol{tag}")); answer(B, b4); answer(C, b4); say(B, b4, "B in b4"); say(C, b4, "C in b4")
a_msg_b1 = adm("select id from messages where bridge_id=%s and user_id=%s", (b1, A))[0][0]
c_msg_b3 = adm("select id from messages where bridge_id=%s and user_id=%s", (b3, C))[0][0]
c_msg_b4 = adm("select id from messages where bridge_id=%s and user_id=%s", (b4, C))[0][0]

print("reports")
r_ab = run(A, "select report_content('user',%s,'harassment','test note')", (B,))[0][0]
check("A reports user B -> report id returned", isinstance(r_ab, int))
r_ca = run(C, "select report_content('message',%s,'spam','')", (str(adm("select id from messages where bridge_id=%s and user_id=%s", (b3, A))[0][0]),))[0][0]
check("C reports A's chat message in their shared bridge", isinstance(r_ca, int))
check("B reports C's message in shared bridge b4", isinstance(run(B, "select report_content('message',%s,'hate')", (str(c_msg_b4),))[0][0], int))
raises("D can't report a message from a club they're not on", D, "select report_content('message',%s,'spam')", (str(c_msg_b4),), "not found")
raises("can't report yourself", B, "select report_content('user',%s,'spam')", (B,), "yourself")
raises("invalid reason rejected", B, "select report_content('user',%s,'boring')", (C,), "reports_reason_check")
raises("unknown type rejected", B, "select report_content('bridge',%s,'spam')", (C,), "unknown report type")
raises("garbage message id rejected", B, "select report_content('message','1; drop table x','spam')", (), "not found")
bitem = adm("select id from library_items where user_id=%s", (B,))[0][0]
run(B, "update profiles set library_visibility='private' where id=%s", (B,))
raises("D can't report B's private library item (can't see it)", D, "select report_content('library_item',%s,'spam')", (str(bitem),), "not found")
run(B, "update profiles set library_visibility='everyone' where id=%s", (B,))
check("D can report B's library item once it's visible to everyone", isinstance(run(D, "select report_content('library_item',%s,'sexual','bad link')", (str(bitem),))[0][0], int))
raises("anon can't file reports", None, "select report_content('user',%s,'spam')", (C,), "permission denied")
raises("users can't read the reports table", B, "select * from reports", (), "permission denied")
raises("users can't insert reports directly", B, "insert into reports (reporter,target_type,target_id,reason) values (%s,'user',%s,'spam')", (B, C), "permission denied")
raises("users can't update reports", A, "update reports set status='dismissed'", (), "permission denied")
raises("users can't delete reports", A, "delete from reports", (), "permission denied")
raises("users can't read the moderation view", B, "select * from private.reports_review", (), "permission denied")
raises("anon can't read the reports table", None, "select * from reports", (), "permission denied")
rv = adm("select target_type, reason, target_name, reporter_name, snapshot from private.reports_review where id=%s", (r_ab,))
check("admin sees the report in private.reports_review with names + snapshot", rv and rv[0][:4] == ("user", "harassment", f"Bob{tag}", f"Alice{tag}") and f"Bob{tag}" in rv[0][4])
check("admin view shows message snapshot text", adm("select snapshot from private.reports_review where id=%s", (r_ca,)) == [("A in b3",)])
for i in range(30 - len(adm("select 1 from reports where reporter=%s", (E,)))):
    run(E, "select report_content('user',%s,'spam')", (C,))
raises("rate limit: 31st report in a day refused", E, "select report_content('user',%s,'spam')", (C,), "too many reports")

print("delete account")
before = {t: adm(f"select count(*) from {t}")[0][0] for t in ("auth.users", "profiles", "bridges", "bridge_members", "answers", "messages", "library_items", "friendships", "blocks", "reports")}
raises("anon can't call delete_my_account", None, "select delete_my_account()", (), "permission denied")
raises("users can't delete other auth users directly", B, "delete from auth.users where id=%s", (A,), "permission denied")
run(A, "select delete_my_account()")
check("A's auth user is gone", adm("select count(*) from auth.users where id=%s", (A,)) == [(0,)])
check("A's profile is gone", adm("select count(*) from profiles where id=%s", (A,)) == [(0,)])
check("A's library is gone", adm("select count(*) from library_items where user_id=%s", (A,)) == [(0,)])
check("A's friendships are gone", adm("select count(*) from friendships where %s in (requester, addressee)", (A,)) == [(0,)])
check("A's blocks are gone", adm("select count(*) from blocks where %s in (blocker, blocked)", (A,)) == [(0,)])
check("A's memberships, answers and messages are gone", adm("select (select count(*) from bridge_members where user_id=%s)+(select count(*) from answers where user_id=%s)+(select count(*) from messages where user_id=%s)", (A, A, A)) == [(0,)])
check("A's solo bridge was deleted", adm("select count(*) from bridges where id=%s", (b2,)) == [(0,)])
r = adm("select created_by, partner_left_at is not null from bridges where id=%s", (b1,))
check("shared bridge A started survives for B: closed, owner cleared", r == [(None, True)])
check("B still sees that bridge + own answers + own message", len(run(B, "select id from bridges where id=%s", (b1,))) == 1
      and len(run(B, "select 1 from answers where bridge_id=%s", (b1,))) == 1 and run(B, "select body from messages where bridge_id=%s", (b1,)) == [("from B",)])
check("bridge A joined (C's) survives for C, closed, C still owner with content", adm("select created_by::text, partner_left_at is not null from bridges where id=%s", (b3,)) == [(C, True)]
      and run(C, "select body from messages where bridge_id=%s", (b3,)) == [("from C",)])
check("unrelated bridge B+C untouched", adm("select partner_left_at from bridges where id=%s", (b4,)) == [(None,)]
      and adm("select count(*) from bridge_members where bridge_id=%s", (b4,)) == [(2,)] and adm("select count(*) from messages where bridge_id=%s", (b4,)) == [(2,)])
check("other users' profiles + libraries untouched", adm("select count(*) from profiles where id in (%s,%s,%s,%s)", (B, C, D, E)) == [(4,)]
      and adm("select count(*) from library_items where user_id=%s", (B,)) == [(1,)])
check("C-D friendship untouched", adm("select count(*) from friendships where %s in (requester,addressee)", (C,)) == [(1,)])
p = run(D, "select owner_name, member_count from preview_bridge(%s)", (t1,))
check("invite preview of the closed bridge: full, owner shown as 'Deleted user'", p == [("Deleted user", 2)])
raises("nobody can join a closed bridge via the old invite", D, "select join_bridge(%s,'Dave')", (t1,), "already has two people")
raises("owner can't add a friend into a closed bridge", C, "select add_friend_to_bridge(%s,%s)", (b3, D), "not found")
check("report A filed is kept (reporter removed); report about A kept with snapshot", adm("select reporter from reports where id=%s", (r_ab,)) == [(None,)]
      and adm("select target_user, snapshot from reports where id=%s", (r_ca,)) == [(None, "A in b3")])
after = {t: adm(f"select count(*) from {t}")[0][0] for t in before}
exp = {"auth.users": -1, "profiles": -1, "bridges": -1, "bridge_members": -3, "answers": -2, "messages": -2, "library_items": -2, "friendships": -1, "blocks": -1, "reports": 0}
check(f"row counts changed only by A's own data {dict((k, after[k]-before[k]) for k in before)}", all(after[k] - before[k] == exp[k] for k in exp))
run(B, "select delete_my_account()")
check("when the last member leaves, the bridge is removed", adm("select count(*) from bridges where id=%s", (b1,)) == [(0,)])
check("B's other bridge with C survives, closed", adm("select partner_left_at is not null from bridges where id=%s", (b4,)) == [(True,)])
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
