"""DB rule tests for group pods (supabase/migrations/20261013120000_group_pods.sql), same harness as test_notifications_rls.py."""
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
adm = lambda sql, p=(): conn.execute(sql, p).fetchall()
tag = uuid.uuid4().hex[:6]
A, B, C, D, E, M = (new_user(n) for n in (f"Ann{tag}", f"Ben{tag}", f"Cat{tag}", f"Dan{tag}", f"Eve{tag}", f"Max{tag}"))
run(A, "select block_user(%s)", (D,))
nt = lambda u, kind: adm("select count(*), coalesce(max(count),0) from notifications where user_id=%s and kind=%s and read_at is null", (u, kind))[0]

print("create")
raises("anon can't create a pod", None, "select create_group_pod('x', %s::uuid[])", ([B],), "permission denied")
raises("needs at least one person", A, "select create_group_pod('Book nerds', '{}'::uuid[])", (), "at least one")
raises("blank name rejected", A, "select create_group_pod('  ', %s::uuid[])", ([B],), "name")
raises("can't add someone you blocked", A, "select create_group_pod('Pod', %s::uuid[])", ([B, D],), "not found")
raises("profane pod name rejected", A, "select create_group_pod('fuck pod', %s::uuid[])", ([B],), "")
P = str(run(A, "select create_group_pod(%s, %s::uuid[])", (f"Pod {tag}", [B, C]))[0][0])
check("A creates a pod with B and C", len(adm("select 1 from group_pod_members where pod_id=%s", (P,))) == 3)
check("A is owner", adm("select role from group_pod_members where pod_id=%s and user_id=%s", (P, A)) == [("owner",)])
check("B and C notified 'pod_added'", nt(B, "pod_added")[0] == 1 and nt(C, "pod_added")[0] == 1)
check("members see the pod", len(run(B, "select id from group_pods where id=%s", (P,))) == 1)
denied("outsider E can't see the pod", E, "select id from group_pods where id=%s", (P,))
denied("outsider E can't see members", E, "select user_id from group_pod_members where pod_id=%s", (P,))
denied("no direct insert into members", E, "insert into group_pod_members (pod_id,user_id,display_name) values (%s,%s,'x')", (P, E))
denied("no direct insert into messages", B, "insert into group_pod_messages (pod_id,user_id,body) values (%s,%s,'x')", (P, B))
denied("no direct update of pod name", B, "update group_pods set name='hacked' where id=%s", (P,))

print("members")
raises("non-owner can't add people", B, "select add_group_members(%s, %s::uuid[])", (P, [E]), "owner")
check("owner adds E", run(A, "select add_group_members(%s, %s::uuid[])", (P, [E])) == [(1,)])
raises("non-owner can't remove people", B, "select remove_group_member(%s,%s)", (P, E), "owner")
run(A, "select remove_group_member(%s,%s)", (P, E)); check("owner removes E", len(adm("select 1 from group_pod_members where pod_id=%s and user_id=%s", (P, E))) == 0)
denied("removed E can't see the pod any more", E, "select id from group_pods where id=%s", (P,))
many = [new_user(f"Many{i}{tag}") for i in range(10)]
raises("max 12 members", A, "select add_group_members(%s, %s::uuid[])", (P, many), "up to 12")
check("…and nobody was added by the failed call", len(adm("select 1 from group_pod_members where pod_id=%s", (P,))) == 3)

print("chat + clips")
check("chat open before anything is shared", run(B, "select send_group_message(%s,'hi all')", (P,))[0][0] > 0)
check("A and C notified of the message", nt(A, "pod_message")[0] == 1 and nt(C, "pod_message")[0] == 1)
run(B, "select send_group_message(%s,'second')", (P,)); check("message notifications grouped (one row, count 2)", nt(C, "pod_message") == (1, 2))
K = str(run(A, "select share_to_group_pod(%s,'Great talk','https://example.org/talk','Podcast','listen!')", (P,))[0][0])
check("B and C notified of the shared clip", nt(B, "pod_clip")[0] == 1 and nt(C, "pod_clip")[0] == 1)
raises("bad URL rejected", A, "select share_to_group_pod(%s,'x','javascript:alert(1)')", (P,), "check")
raises("outsider can't share", E, "select share_to_group_pod(%s,'x','https://example.org/x')", (P,), "not found")
raises("chat locked for B until B answers the newest clip", B, "select send_group_message(%s,'locked?')", (P,), "answer the newest")
denied("…and B can't read the chat while locked", B, "select id from group_pod_messages where pod_id=%s", (P,))
run(A, "select answer_group_clip(%s,'moment','surprise','takeaway')", (K,))
denied("B can't read A's answers before answering", B, "select a1 from group_pod_answers where clip_id=%s and user_id=%s", (K, A))
raises("hate speech in answers rejected", B, "select answer_group_clip(%s,'nigger','b','c')", (K,), "")
run(B, "select answer_group_clip(%s,'b1','b2','b3')", (K,))
check("after answering, B reads A's answers", run(B, "select a1 from group_pod_answers where clip_id=%s and user_id=%s", (K, A)) == [("moment",)])
raises("can't answer twice", B, "select answer_group_clip(%s,'x','y','z')", (K,), "already")
check("B's chat unlocked", run(B, "select send_group_message(%s,'what a talk')", (P,))[0][0] > 0)
check("B now reads the whole chat", len(run(B, "select id from group_pod_messages where pod_id=%s", (P,))) == 3)
run(B, "select send_group_message(%s,'shit happens')", (P,))
check("profanity in group chat is masked", run(A, "select body from group_pod_messages where pod_id=%s order by id desc limit 1", (P,)) == [("s*** happens",)])
denied("C (not answered) can't read chat yet", C, "select id from group_pod_messages where pod_id=%s", (P,))
raises("outsider can't answer", E, "select answer_group_clip(%s,'x','y','z')", (K,), "not found")

print("blocks")
run(C, "select answer_group_clip(%s,'c1','c2','c3')", (K,))
run(C, "select block_user(%s)", (B,))
check("C no longer sees B's messages", all(str(r[0]) != B for r in run(C, "select user_id from group_pod_messages where pod_id=%s", (P,))))
check("…nor B's answers", run(C, "select count(*) from group_pod_answers where clip_id=%s and user_id=%s", (K, B)) == [(0,)])
before = nt(C, "pod_message")[1]; run(B, "select send_group_message(%s,'anyone?')", (P,))
check("C gets no notification for B's message", nt(C, "pod_message")[1] == before)
check("A still sees B's messages", any(str(r[0]) == B for r in run(A, "select user_id from group_pod_messages where pod_id=%s", (P,))))

print("rate limits")
Q = str(run(M, "select create_group_pod(%s, %s::uuid[])", (f"Spam {tag}", [many[0]]))[0][0])
for i in range(20): run(M, "select send_group_message(%s,%s)", (Q, f"m{i}"))
raises("21st message in a minute is refused", M, "select send_group_message(%s,'too fast')", (Q,), "very fast")
for i in range(20): run(M, "select share_to_group_pod(%s,%s,%s)", (Q, f"c{i}", f"https://example.org/{i}"))
raises("21st share in an hour is refused", M, "select share_to_group_pod(%s,'x','https://example.org/x')", (Q,), "a lot of clips")

print("leave / ownership")
run(A, "select leave_group_pod(%s)", (P,))
check("owner leaves -> longest-standing member becomes owner", adm("select owner::text from group_pods where id=%s", (P,))[0][0] in (B, C) and len(adm("select 1 from group_pod_members where pod_id=%s and role='owner'", (P,))) == 1)
denied("A can't read the pod after leaving", A, "select id from group_pods where id=%s", (P,))
run(B, "select leave_group_pod(%s)", (P,)); run(C, "select leave_group_pod(%s)", (P,))
check("last member leaves -> pod deleted (with its clips, chat, notifications)", adm("select count(*) from group_pods where id=%s", (P,)) == [(0,)] and adm("select count(*) from notifications where group_pod_id=%s", (P,)) == [(0,)])
R = str(run(E, "select create_group_pod(%s, %s::uuid[])", (f"Del {tag}", [A]))[0][0])
conn.execute("delete from auth.users where id=%s", (E,))
check("owner deletes account -> remaining member becomes owner", adm("select owner::text from group_pods where id=%s", (R,)) == [(A,)])

print("2-person pods untouched")
b = run(A, "select id, invite_token from create_bridge(%s,'Old style','https://example.org/old')", (f"Ann{tag}",))[0]
check("create_bridge still works", b[0] is not None)
check("join_bridge still works", run(B, "select join_bridge(%s,%s)", (b[1], f"Ben{tag}"))[0][0] is not None)
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
