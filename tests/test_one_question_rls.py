"""DB tests for one question + 0–10 rating (20261014100000_one_question.sql)."""
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
tag = str(uuid.uuid4().int)[:6]  # digits only: random hex can trip the name filter
A, B, C, E = (new_user(n) for n in (f"Ann{tag}", f"Ben{tag}", f"Cat{tag}", f"Eve{tag}"))
print("2-person pods")
b = run(A, "select id, invite_token from create_bridge(%s,'One Q','https://example.org/oneq')", (f"Ann{tag}",))[0]; bid = str(b[0])
run(B, "select join_bridge(%s,%s)", (b[1], f"Ben{tag}"))
raises("rating above 10 rejected", A, "insert into answers (bridge_id,user_id,a3,rating) values (%s,auth.uid(),'take',11)", (bid,), "check")
raises("negative rating rejected", A, "insert into answers (bridge_id,user_id,a3,rating) values (%s,auth.uid(),'take',-1)", (bid,), "check")
raises("new-style answer without rating rejected", A, "insert into answers (bridge_id,user_id,a3) values (%s,auth.uid(),'take')", (bid,), "a1_or_rating")
raises("blank answer still rejected", A, "insert into answers (bridge_id,user_id,a3,rating) values (%s,auth.uid(),'   ',5)", (bid,), "check")
check("one answer + rating accepted", run(A, "insert into answers (bridge_id,user_id,a3,rating) values (%s,auth.uid(),'Great takeaway',0)", (bid,)) == 1)
check("answered_at set (chat unlocks after you answer)", adm("select answered_at is not null from bridge_members where bridge_id=%s and user_id=%s", (bid, A)) == [(True,)])
check("A can chat right after answering", run(A, "insert into messages (bridge_id,user_id,body) values (%s,auth.uid(),'hi')", (bid,)) == 1)
denied("B can't see A's rating before answering", B, "select rating from answers where bridge_id=%s and user_id=%s", (bid, A))
check("old 3-answer style (live app) still accepted, no rating", run(B, "insert into answers (bridge_id,user_id,a1,a2,a3) values (%s,auth.uid(),'m','s','t')", (bid,)) == 1)
check("B now sees A's answer + rating", run(B, "select a3, rating from answers where bridge_id=%s and user_id=%s", (bid, A)) == [("Great takeaway", 0)])
print("group pods")
P = str(run(A, "select create_group_pod(%s, %s::uuid[])", (f"OneQ {tag}", [B, C]))[0][0])
K = str(run(A, "select share_to_group_pod(%s,'Ep','https://example.org/ep','Podcast','')", (P,))[0][0])
raises("v2: rating required", A, "select answer_group_clip_v2(%s,'take',null)", (K,), "rating")
raises("v2: rating 0..10", A, "select answer_group_clip_v2(%s,'take',11)", (K,), "rating")
raises("v2: answer required", A, "select answer_group_clip_v2(%s,'  ',5)", (K,), "answer the question")
raises("v2: outsider can't answer", E, "select answer_group_clip_v2(%s,'x',5)", (K,), "not found")
raises("v2: hate speech rejected", A, "select answer_group_clip_v2(%s,'nigger',5)", (K,), "")
run(A, "select answer_group_clip_v2(%s,'That was shit hot',8)", (K,))
check("v2 stores a3 + rating (masked)", adm("select a1, a3, rating from group_pod_answers where clip_id=%s and user_id=%s", (K, A)) == [(None, "That was s*** hot", 8)])
raises("v2: can't answer twice", A, "select answer_group_clip_v2(%s,'again',3)", (K,), "already")
check("A's group chat opens after answering", run(A, "select send_group_message(%s,'hello')", (P,))[0][0] > 0)
denied("B can't see ratings before answering", B, "select rating from group_pod_answers where clip_id=%s", (K,))
run(B, "select answer_group_clip(%s,'b1','b2','b3')", (K,)); check("old 3-answer RPC still works (live app)", True)
run(C, "select answer_group_clip_v2(%s,'C take',5)", (K,))
check("members see everyone's ratings for the average", sorted(r[0] for r in run(C, "select rating from group_pod_answers where clip_id=%s and rating is not null", (K,))) == [5, 8])
for u in (A, B, C, E): conn.execute("delete from auth.users where id=%s", (u,))
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
