"""DB rule tests for direct bridges + notifications (same harness as test_social_rls.py)."""
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
befriend(A, B)
run(A, "select block_user(%s)", (D,))
# --- direct bridges
S = lambda u, to, t="Talk", note="": run(u, "select send_direct_bridge(%s,%s,%s,'Video','','',%s)", (to, t, f"https://example.org/{t}-{tag}", note))[0][0]
b1 = str(S(A, C, "Stranger", "you might like this"))   # not friends: allowed
check("send to a non-friend works", bool(b1))
check("sender sees it in their bridges (owner)", run(A, "select direct_to_name, direct_status from bridges where id=%s", (b1,)) == [(f"Carol{tag}", "pending")])
check("recipient can't read the bridge row before accepting", run(C, "select id from bridges where id=%s", (b1,)) == [])
inc = run(C, "select id, sender_name, note from my_incoming_bridges()")
check("recipient lists it as incoming with note", [(str(i), n, t) for i, n, t in inc] == [(b1, f"Alice{tag}", "you might like this")])
check("others don't see it as incoming", run(B, "select id from my_incoming_bridges()") == [])
nc = run(C, "select kind, actor_name, title from notifications")
check("recipient got a direct_bridge notification", ("direct_bridge", f"Alice{tag}", "Stranger") in nc)
raises("blocked (either way) -> not found", A, "select send_direct_bridge(%s,'x','https://example.org/x')", (D,), "not found")
raises("blocked person can't send to blocker", D, "select send_direct_bridge(%s,'x','https://example.org/x')", (A,), "not found")
raises("can't send to yourself", A, "select send_direct_bridge(%s,'x','https://example.org/x')", (A,), "yourself")
raises("someone else can't accept it", B, "select respond_direct_bridge(%s,true)", (b1,), "not found")
S(A, C, "Two"); S(A, C, "Three")
raises("max 3 pending to the same person", A, "select send_direct_bridge(%s,'Four','https://example.org/four')", (C,), "3 bridges waiting")
raises("hate term in the note is refused", A, "select send_direct_bridge(%s,'x','https://example.org/x','Video','','',%s)", (B, "x " + (adm("select term from moderation_terms where category='hate' limit 1") or [("zzzz",)])[0][0]), "respectful")
check("accept joins the bridge", str(run(C, "select respond_direct_bridge(%s,true)", (b1,))[0][0]) == b1)
check("recipient now reads it", len(run(C, "select id from bridges where id=%s", (b1,))) == 1)
check("accepted bridge leaves incoming list", b1 not in [str(r[0]) for r in run(C, "select id from my_incoming_bridges()")])
check("sender notified that they joined", ("joined", f"Carol{tag}") in run(A, "select kind, actor_name from notifications"))
answer(C, b1); check("partner answered -> notification", ("answered", f"Carol{tag}") in run(A, "select kind, actor_name from notifications"))
answer(A, b1); say(C, b1, "hi"); say(C, b1, "again")
m = run(A, "select count from notifications where kind='message' and bridge_id=%s and read_at is null", (b1,))
check("chat messages bump one unread notification", m == [(2,)])
d = run(C, "select id from my_incoming_bridges()")[0][0]
check("decline", run(C, "select respond_direct_bridge(%s,false)", (d,)) == [(None,)] and d not in [r[0] for r in run(C, "select id from my_incoming_bridges()")])
# --- notifications RLS
denied("can't read someone else's notifications", B, "select id from notifications where user_id=%s", (A,))
denied("can't mark someone else's read", B, "update notifications set read_at=now() where user_id=%s", (A,))
raises("can't insert notifications directly", B, "insert into notifications (user_id, kind) values (%s,'message')", (A,), "permission")
raises("can't change other columns", A, "update notifications set title='x'", (), "permission")
raises("can't call the private notify helper", B, "select private.notify(%s,'message',%s,null,'x')", (A, B), "permission")
denied("anon reads nothing", None, "select id from notifications")
check("mark own read", run(A, "select mark_notifications_read(null)")[0][0] >= 3 and run(A, "select count(*) from notifications where read_at is null") == [(0,)])
run(E, "select send_friend_request(%s)", (B,)); check("friend request -> notification", ("friend_request", f"Eve{tag}") in run(B, "select kind, actor_name from notifications"))
run(B, "select respond_friend_request(%s,true)", (E,)); check("accepted -> notification", ("friend_accepted", f"Bob{tag}") in run(E, "select kind, actor_name from notifications"))
check("blocked people don't notify each other", run(A, "select count(*) from notifications where actor=%s", (D,)) == [(0,)])
# invite link still works for direct bridges sent to someone else
b5 = str(S(B, C, "ByLink")); tok = adm("select invite_token from bridges where id=%s", (b5,))[0][0]
check("invite link still joins", str(run(E, "select join_bridge(%s,%s)", (tok, f"Eve{tag}"))[0][0]) == b5)
check("...and the direct send is no longer pending", adm("select direct_status from bridges where id=%s", (b5,)) == [("declined",)])
print(f"\n{passed} passed, {failed} failed"); raise SystemExit(1 if failed else 0)
