"""DB tests for list_people (20261014090000_people_row.sql)."""
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
A, B, C, D, E = (new_user(n) for n in (f"Ann{tag}", f"Ben{tag}", f"Cat{tag}", f"Dan{tag}", f"Eve{tag}"))
S = new_user(f"SmokeTest{tag}"); G = new_user("Guest"); N = new_user(None)
run(A, "select block_user(%s)", (D,)); run(E, "select block_user(%s)", (A,))
ids = lambda u, *a: [str(r[0]) for r in run(u, "select id from list_people(" + ",".join(["%s"] * len(a)) + ")", a)]
L = ids(A)
print("list_people")
raises("anon can't list people", None, "select * from list_people()", (), "permission denied")
check("sees other named people", B in L and C in L)
check("excludes yourself", A not in L)
check("excludes people you blocked", D not in L)
check("excludes people who blocked you", E not in L)
check("B still sees D and E (blocks are per pair)", D in ids(B) and E in ids(B))
check("excludes Smoke* test users", S not in L)
check("excludes unnamed guests ('Guest' / no profile)", G not in L and N not in L)
check("newest first", L.index(C) < L.index(B))
conn.execute("delete from auth.users where id=%s", (C,)); check("excludes deleted accounts", C not in ids(A))
print("pagination")
extra = [new_user(f"Pg{tag}{i:02d}") for i in range(65)]
p1 = run(A, "select id, created_at from list_people(null, null, 30)"); check("page size 30", len(p1) == 30)
p2 = run(A, "select id, created_at from list_people(%s, %s, 30)", (p1[-1][1], p1[-1][0])); check("next page continues with no overlap", len(p2) == 30 and not ({r[0] for r in p1} & {r[0] for r in p2}))
check("pages stay in newest-first order", p1[-1][1] >= p2[0][1])
check("limit capped at 50", len(run(A, "select id from list_people(null, null, 500)")) == 50)
check("no profile fields beyond name/username/created_at", [d.name for d in conn.execute("select * from list_people() limit 0").description] == ["id", "display_name", "username", "created_at"])
for u in extra + [A, B, D, E, S, G, N]: conn.execute("delete from auth.users where id=%s", (u,))
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
