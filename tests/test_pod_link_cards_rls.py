"""DB tests for pod link cards (20261016120000_pod_link_cards.sql): member-only, set-once preview cache on bridges and group pod clips via cache_pod_preview, filter + mask, invite preview never leaks URL/thumbnail, YouTube backfill."""
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
A, B, C = new_user(f"Ann{tag}"), new_user(f"Ben{tag}"), new_user(f"Cat{tag}")
YT = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
b = run(A, "select id, invite_token from public.create_bridge('Ann','Talk',%s,'Podcast','Science','','Ben','')", (f"https://example.org/ep{tag}",))[0]
bid, tok = str(b[0]), b[1]
for t in ("bridges", "group_pod_clips"):
    cols = [r[0] for r in adm("select column_name from information_schema.columns where table_schema='public' and table_name=%s and column_name in ('thumb_url','preview_title','preview_site','preview_at') and is_nullable='YES'", (t,))]
    check(f"{t}: 4 new nullable columns", len(cols) == 4)
pv = run(None, "select to_jsonb(p) from preview_bridge_v2(%s) p", (tok,))[0][0]
check("invite preview (non-member) has no URL/thumbnail/preview columns", not pv.get("clip_url") and not any(k in pv for k in ("thumb_url", "preview_title", "preview_site")))
raises("non-member can't cache a pod preview", B, "select cache_pod_preview('bridge', %s, 'https://img.example.com/a.jpg', 'x', 'y')", (bid,), "not a member")
raises("anon can't call cache_pod_preview", None, "select cache_pod_preview('bridge', %s, null, null, null)", (bid,), "permission")
denied("non-member can't read the bridge row (no URL/thumbnail)", B, "select clip_url, thumb_url from bridges where id=%s", (bid,))
raises("member can't UPDATE preview columns directly", A, "update bridges set thumb_url='https://x.example.com/a.jpg' where id=%s", (bid,), "permission")
raises("adult-host thumbnail rejected", A, "select cache_pod_preview('bridge', %s, 'https://www.pornhub.com/t.jpg', 't', 's')", (bid,), "can't be shared")
check("member caches once", run(A, "select cache_pod_preview('bridge', %s, 'https://img.example.com/a.jpg', 'what the fuck', 'Site')", (bid,)) == [(True,)])
r = adm("select thumb_url, preview_title, preview_site, preview_at is not null from bridges where id=%s", (bid,))[0]
check("cached on the bridge row, title masked", r[0] == "https://img.example.com/a.jpg" and "fuck" not in r[1] and r[2] == "Site" and r[3])
check("set-once: second write is a no-op", run(A, "select cache_pod_preview('bridge', %s, 'https://img.example.com/b.jpg', 'x', 'y')", (bid,)) == [(False,)] and adm("select thumb_url from bridges where id=%s", (bid,))[0][0].endswith("/a.jpg"))
raises("http thumbnail ignored -> null (not rejected), bad kind rejected", A, "select cache_pod_preview('nope', %s, null, null, null)", (bid,), "bad kind")
run(B, "select join_bridge(%s, 'Ben')", (tok,))
check("member (after join) reads the cached preview", run(B, "select thumb_url from bridges where id=%s", (bid,)) == [("https://img.example.com/a.jpg",)])
P = str(run(A, "select create_group_pod(%s, %s::uuid[])", (f"Pod {tag}", [B]))[0][0])
K = str(run(A, "select share_to_group_pod(%s,'Great talk',%s,'Video','')", (P, f"https://example.org/g{tag}"))[0][0])
raises("non-member can't cache a group clip preview", C, "select cache_pod_preview('group_clip', %s, null, 't', 's')", (K,), "not a member")
denied("non-member can't read the group clip", C, "select url, thumb_url from group_pod_clips where id=%s", (K,))
check("group member caches clip preview", run(B, "select cache_pod_preview('group_clip', %s, null, 'Title', 'Site')", (K,)) == [(True,)])
check("group clip row cached (null thumb = miss marker)", adm("select thumb_url, preview_title, preview_at is not null from group_pod_clips where id=%s", (K,))[0] == (None, "Title", True))
# backfill statement (same as the migration) on fresh rows
K2 = str(run(A, "select share_to_group_pod(%s,'YT',%s,'Video','')", (P, YT))[0][0])
b2 = str(run(A, "select id from public.create_bridge('Ann','YT',%s,'Video','Science','','Cat','')", (f"https://youtu.be/dQw4w9WgXcQ?si={tag}",))[0][0])
mig = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../supabase/migrations/20261016120000_pod_link_cards.sql")).read()
conn.execute(mig[mig.index("-- Backfill YouTube"):])
check("backfill: group clip YouTube thumbnail", adm("select thumb_url, preview_site from group_pod_clips where id=%s", (K2,))[0] == ("https://img.youtube.com/vi/aqz-KE-bpKQ/hqdefault.jpg", "YouTube"))
check("backfill: bridge youtu.be thumbnail", adm("select thumb_url from bridges where id=%s", (b2,))[0][0] == "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg")
check("backfill didn't touch already-cached rows", adm("select thumb_url from bridges where id=%s", (bid,))[0][0].endswith("/a.jpg"))
print(f"\npod link cards: {passed} passed, {failed} failed"); raise SystemExit(1 if failed else 0)
