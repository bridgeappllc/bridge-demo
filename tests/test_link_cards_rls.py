"""DB tests for link cards (20261016090000_link_cards.sql): owner-only preview cache writes (RLS + column grants),
https-only thumbnails that must pass the link filter, masked preview titles, YouTube backfill expression."""
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
iid = run(A, "insert into library_items (url, title) values (%s, 'Talk') returning id", (f"https://example.com/talk{tag}",))[0][0]
cols = [r[0] for r in adm("select column_name from information_schema.columns where table_schema='public' and table_name='library_items' and column_name in ('thumb_url','preview_title','preview_site','preview_at') and is_nullable='YES'")]
check("4 new nullable columns", sorted(cols) == ["preview_at", "preview_site", "preview_title", "thumb_url"])
r = run(A, "update library_items set thumb_url='https://img.youtube.com/vi/aqz-KE-bpKQ/hqdefault.jpg', preview_title='A title', preview_site='Site', preview_at=now() where id=%s", (iid,))
check("owner can cache a preview", r == 1)
check("owner sees it", run(A, "select thumb_url, preview_site from library_items where id=%s", (iid,))[0] == ("https://img.youtube.com/vi/aqz-KE-bpKQ/hqdefault.jpg", "Site"))
denied("another user can't overwrite the cache (RLS)", B, "update library_items set thumb_url='https://evil.example/x.jpg' where id=%s", (iid,))
check("cache unchanged after other user's attempt", adm("select thumb_url from library_items where id=%s", (iid,))[0][0].startswith("https://img.youtube.com/"))
denied("anon can't update", None, "update library_items set preview_title='x' where id=%s", (iid,))
raises("http (not https) thumbnail rejected", A, "update library_items set thumb_url='http://img.example.com/a.jpg' where id=%s", (iid,), "check")
raises("javascript: thumbnail rejected", A, "update library_items set thumb_url='javascript:alert(1)' where id=%s", (iid,), "check")
raises("quote/HTML in thumbnail rejected", A, "update library_items set thumb_url='https://a.com/x\"onerror=alert(1)' where id=%s", (iid,), "check")
raises("adult-host thumbnail rejected by link filter", A, "update library_items set thumb_url='https://www.pornhub.com/t.jpg' where id=%s", (iid,), "can't be shared")
raises("shortener thumbnail rejected", A, "update library_items set thumb_url='https://bit.ly/abc' where id=%s", (iid,), "can't be shared")
raises("over-long preview title rejected", A, "update library_items set preview_title=repeat('a', 301) where id=%s", (iid,), "check")
run(A, "update library_items set preview_title='what the fuck' where id=%s", (iid,))
check("preview title gets the profanity mask", "fuck" not in adm("select preview_title from library_items where id=%s", (iid,))[0][0])
raises("still can't change created_at/user_id (grants unchanged)", A, "update library_items set user_id=%s where id=%s", (B, iid), "permission")
j = run(A, "insert into library_items (url, title, thumb_url, preview_site, preview_at) values (%s, 'Ins', 'https://i.ytimg.com/vi/x/hq.jpg', 'YouTube', now()) returning thumb_url", (f"https://www.youtube.com/watch?v=abcdefghij{tag[0]}",))
check("insert with preview columns allowed for owner", j[0][0] == "https://i.ytimg.com/vi/x/hq.jpg")
# backfill expression (same as the migration) on a scratch set
q = """select coalesce(substring(u from '^https?://(?:www\\.)?youtu\\.be/([A-Za-z0-9_-]{11})'),
  substring(u from '^https?://(?:www\\.|m\\.|music\\.)?youtube\\.com/watch\\?(?:[^#]*&)?v=([A-Za-z0-9_-]{11})'),
  substring(u from '^https?://(?:www\\.|m\\.)?youtube\\.com/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})')) from (values (%s)) v(u)"""
for u, want in [("https://youtu.be/lhPzqAIQV-U?is=2Xc7", "lhPzqAIQV-U"), ("https://www.youtube.com/watch?v=FEUjcRWfu3c", "FEUjcRWfu3c"), ("https://m.youtube.com/watch?feature=x&v=A8wJc7vHcTs", "A8wJc7vHcTs"),
                ("https://youtube.com/shorts/Oos4ojutOMM?si=1", "Oos4ojutOMM"), ("https://podcasts.apple.com/us/podcast/x/id1", None), ("https://notyoutube.com/watch?v=FEUjcRWfu3c", None)]:
    check(f"backfill id {u} -> {want}", adm(q, (u,))[0][0] == want)
print(f"\nlink cards: {passed} passed, {failed} failed"); raise SystemExit(1 if failed else 0)
