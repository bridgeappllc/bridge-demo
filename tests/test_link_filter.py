"""DB tests for the link filter (20261015090000_link_filter.sql + supabase/seed/blocked_domains.sql)."""
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
            if uid == "service":
                cur.execute("set local role service_role"); cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": "service_role"}),))
            elif uid is None:
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
def confirm(u, email): conn.execute("update auth.users set email=%s, email_confirmed_at=now(), is_anonymous=false where id=%s", (email, u))
A, B = new_user(f"Ann{tag}"), new_user(f"Ben{tag}")
for u, n in ((A, "a"), (B, "b")): confirm(u, f"{n}-{tag}@test.local")
BAD = ["https://www.pornhub.com/view_video.php?v=1", "HTTPS://WWW.XVIDEOS.COM/", "https://m.xhamster.com/x", "https://%70ornhub.com/", "https://pornhub。com/",
       "https://user:pw@pornhub.com:443/", "https://pornhub.com./", "https://bit.ly/3abc", "https://linktr.ee/someone", "https://my-free-porn-tube.example/",
       "https://hot-sexcam.example/", "https://onlyfans.com/user"]
GOOD = ["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://open.spotify.com/episode/1", "https://www.essex.ac.uk/news", "https://sussex.ac.uk/",
        "https://www.nytimes.com/2026/10/01/health/sex-education.html", "https://münchen.de/", "https://podcasts.apple.com/us/podcast/x/id1", "https://youtu.be/abc"]
print("rules")
check(f"seed loaded ({adm('select count(*) from blocked_domains where category=%s', ('adult',))[0][0]} adult domains)", adm("select count(*) from blocked_domains where category='adult'")[0][0] > 40000)
for u in BAD: check(f"blocked: {u}", run(A, "select link_ok(%s)", (u,)) == [(False,)])
for u in GOOD: check(f"allowed: {u}", run(A, "select link_ok(%s)", (u,)) == [(True,)])
check("anon can call link_ok (pre-sign-up form checks)", run(None, "select link_ok('https://pornhub.com')") == [(False,)])
check("IDN host is normalized to punycode", adm("select private.link_host('https://WWW.Bücher.de/x')") == [("xn--bcher-kva.de",)])
print("admin-only tables")
for t in ("blocked_domains", "blocked_link_keywords", "allowed_domains"):
    denied(f"users can't read {t}", A, f"select * from {t} limit 1"); denied(f"users can't write {t}", A, f"insert into {t} (domain) values ('x.example')" if t != "blocked_link_keywords" else f"insert into {t} (keyword) values ('abcd')")
print("enforced on every table")
P = "https://www.pornhub.com/x"
raises("bridges (create_bridge)", A, "select * from create_bridge(%s,'t',%s)", (f"Ann{tag}", P), "can't be shared")
raises("bridges (direct send)", A, "select send_direct_bridge(%s,'t',%s)", (B, P), "can't be shared")
raises("library_items", A, "insert into library_items (user_id,url,title) values (auth.uid(),%s,'t')", (P,), "can't be shared")
pod = str(run(A, "select create_group_pod(%s, %s::uuid[])", (f"Pod {tag}", [B]))[0][0])
raises("group_pod_clips (share)", A, "select share_to_group_pod(%s,'t',%s,'Podcast','')", (pod, P), "can't be shared")
try: run(A, "select * from create_bridge(%s,'t','https://bit.ly/x')", (f"Ann{tag}",)); check("shortener -> unexpectedly ok", False)
except psycopg.Error as e: check("error carries detail link_filter:shortener", "link_filter:shortener" in (e.diag.message_detail or ""))
b = run(A, "select id from create_bridge(%s,'Good clip','https://www.youtube.com/watch?v=1')", (f"Ann{tag}",))[0][0]
li = run(A, "insert into library_items (user_id,url,title) values (auth.uid(),'https://open.spotify.com/episode/9','Ep') returning id")[0][0]
check("clean links still work everywhere", b is not None and li is not None and run(A, "select share_to_group_pod(%s,'t','https://youtu.be/x','Video','')", (pod,)) != [])
raises("changing a clean URL to an adult one is blocked (trigger runs even for service-role writes)", "service", "update library_items set url=%s where id=%s", (P, li), "can't be shared")
print("existing rows")
conn.execute("alter table library_items disable trigger library_items_link_filter")
old = adm("insert into library_items (user_id,url,title) values (%s,%s,'legacy') returning id", (A, P))[0][0]
conn.execute("alter table library_items enable trigger library_items_link_filter")
check("an existing blocked row isn't touched by unrelated updates (note edit ok)", run(A, "update library_items set note='edited' where id=%s", (old,)) == 1)
check("…and isn't deleted", adm("select count(*) from library_items where id=%s", (old,)) == [(1,)])
print("titles / notes")
bid = run(A, "select id from create_bridge(%s,'what the fuck','https://example.org/t')", (f"Ann{tag}",))[0][0]; t = adm("select clip_title from bridges where id=%s", (bid,))
check(f"bridge clip titles now go through the word filter (masked: {t})", bool(t) and "fuck" not in t[0][0])
raises("hate terms in a bridge clip title are blocked", A, "select * from create_bridge(%s,'heil hitler','https://example.org/h')", (f"Ann{tag}",), "respectful")
for u in (A, B): conn.execute("delete from auth.users where id=%s", (u,))
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
