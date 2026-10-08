"""RLS / RPC tests for supabase/schema.sql against a real Postgres that has the
Supabase auth schema (created by running the real GoTrue binary's migrations)
plus Supabase's anon/authenticated roles.  Each "user" is simulated exactly the
way PostgREST does it: SET ROLE authenticated + request.jwt.claims."""
import json, os, sys, uuid, psycopg
DSN = os.environ.get("DSN", "postgresql://postgres@127.0.0.1:54322/postgres")
conn = psycopg.connect(DSN, autocommit=True)
passed = failed = 0

def new_user(anon=True):
    uid = str(uuid.uuid4())
    conn.execute("insert into auth.users (id, instance_id, aud, role, is_anonymous, created_at, updated_at) values (%s, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', %s, now(), now())", (uid, anon))
    return uid

def run(uid, sql, params=()):
    """Run sql as user uid (None = anon key, no session). Returns rows or raises."""
    with conn.transaction():
        with conn.cursor() as cur:
            if uid is None:
                cur.execute("set local role anon"); cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": "anon"}),))
            else:
                cur.execute("set local role authenticated"); cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": uid, "role": "authenticated", "is_anonymous": True}),))
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else cur.rowcount

def check(name, cond):
    global passed, failed
    if cond: passed += 1; print("  PASS", name)
    else: failed += 1; print("  FAIL", name)

def denied(name, uid, sql, params=()):
    try:
        r = run(uid, sql, params)
        ok = (r == 0 or r == [])          # silently filtered by RLS also counts as denied
        check(f"{name} (filtered: {r})" if ok else f"{name} -> unexpectedly allowed: {r}", ok)
    except psycopg.Error as e:
        check(f"{name} (error: {str(e).splitlines()[0][:70]})", True)

paul, sam, eve, mallory = new_user(), new_user(), new_user(), new_user()
print("create / preview / join")
b = run(paul, "select id, invite_token from public.create_bridge('Paul','Some podcast','https://example.org/ep1','Podcast','Politics','','Sam','5')")[0]
bid, tok = str(b[0]), b[1]
check("owner creates bridge, gets 32-char token", len(tok) == 32)
check("owner sees bridge", len(run(paul, "select * from bridges where id=%s", (bid,))) == 1)
pv = run(None, "select owner_name, clip_title, member_count, is_member from preview_bridge(%s)", (tok,))
check("anon-key preview with token shows owner+title only", pv == [("Paul", "Some podcast", 1, False)])
check("preview with wrong token returns nothing", run(None, "select * from preview_bridge('nope')") == [])
denied("anon cannot select bridges", None, "select * from bridges")
denied("anon cannot create bridge", None, "select public.create_bridge('x','t','https://a.b')")
denied("anon cannot join", None, "select public.join_bridge(%s,'x')", (tok,))
denied("outsider cannot see bridge", eve, "select * from bridges where id=%s", (bid,))
denied("outsider cannot see members", eve, "select * from bridge_members where bridge_id=%s", (bid,))
denied("join with wrong token", sam, "select public.join_bridge('deadbeef','Sam')")
denied("cannot insert membership directly", eve, "insert into bridge_members (bridge_id,user_id,display_name,role) values (%s,%s,'Eve','friend')", (bid, eve))
denied("cannot insert bridge directly", eve, "insert into bridges (created_by,clip_title,clip_url) values (%s,'t','https://x.y')", (eve,))
check("friend joins with token", str(run(sam, "select public.join_bridge(%s,'Sam')", (tok,))[0][0]) == bid)
check("re-join is idempotent", str(run(sam, "select public.join_bridge(%s,'Sam')", (tok,))[0][0]) == bid)
denied("3rd person cannot join (max 2)", eve, "select public.join_bridge(%s,'Eve')", (tok,))
check("friend sees both members", len(run(sam, "select * from bridge_members where bridge_id=%s", (bid,))) == 2)
denied("member cannot update bridge", sam, "update bridges set clip_title='hacked' where id=%s", (bid,))
denied("member cannot change other member", sam, "update bridge_members set display_name='x' where bridge_id=%s", (bid,))
denied("friend cannot delete bridge", sam, "delete from bridges where id=%s", (bid,))

print("answers / ratings / reveal rules")
denied("outsider cannot answer", eve, "insert into answers (bridge_id,a1,a2,a3) values (%s,'a','b','c')", (bid,))
denied("cannot answer as someone else", sam, "insert into answers (bridge_id,user_id,a1,a2,a3) values (%s,%s,'a','b','c')", (bid, paul))
denied("cannot rate before answering", paul, "insert into ratings (bridge_id,score) values (%s,5)", (bid,))
denied("blank answers rejected", paul, "insert into answers (bridge_id,a1,a2,a3) values (%s,'  ','b','c')", (bid,))
run(paul, "insert into answers (bridge_id,a1,a2,a3) values (%s,'p1','p2','p3')", (bid,))
check("owner sees own answers", len(run(paul, "select * from answers where bridge_id=%s", (bid,))) == 1)
denied("friend can't see owner's answers before answering", sam, "select * from answers where bridge_id=%s and user_id=%s", (bid, paul))
check("...but sees owner's progress flag", run(sam, "select answered_at is not null from bridge_members where bridge_id=%s and user_id=%s", (bid, paul)) == [(True,)])
denied("answers are final (no update)", paul, "update answers set a1='edited' where bridge_id=%s", (bid,))
denied("forged created_at rejected", sam, "insert into answers (bridge_id,a1,a2,a3,created_at) values (%s,'a','b','c','2000-01-01')", (bid,))
run(sam, "insert into answers (bridge_id,a1,a2,a3) values (%s,'s1','s2','s3')", (bid,))
check("after answering, friend sees both answers", len(run(sam, "select * from answers where bridge_id=%s", (bid,))) == 2)
check("owner sees both answers", len(run(paul, "select * from answers where bridge_id=%s", (bid,))) == 2)
denied("outsider sees no answers", eve, "select * from answers where bridge_id=%s", (bid,))
denied("score out of range rejected", paul, "insert into ratings (bridge_id,score) values (%s,11)", (bid,))
run(paul, "insert into ratings (bridge_id,score) values (%s,3)", (bid,))
denied("friend can't see owner's rating before rating", sam, "select * from ratings where bridge_id=%s and user_id=%s", (bid, paul))
denied("rating is final (no update)", paul, "update ratings set score=9 where bridge_id=%s", (bid,))

print("chat")
denied("friend can't chat before rating", sam, "insert into messages (bridge_id,body) values (%s,'hi')", (bid,))
run(paul, "insert into messages (bridge_id,body) values (%s,'hello from Paul')", (bid,))
denied("friend can't read chat before rating", sam, "select * from messages where bridge_id=%s", (bid,))
run(sam, "insert into ratings (bridge_id,score) values (%s,8)", (bid,))
check("after rating, friend sees both ratings", sorted(r[0] for r in run(sam, "select score from ratings where bridge_id=%s", (bid,))) == [3, 8])
check("after rating, friend reads chat", [r[0] for r in run(sam, "select body from messages where bridge_id=%s", (bid,))] == ["hello from Paul"])
run(sam, "insert into messages (bridge_id,body) values (%s,'hi Paul')", (bid,))
check("owner reads friend's reply", [r[0] for r in run(paul, "select body from messages where bridge_id=%s order by id", (bid,))] == ["hello from Paul", "hi Paul"])
denied("cannot post as other user", sam, "insert into messages (bridge_id,user_id,body) values (%s,%s,'fake')", (bid, paul))
denied("cannot edit messages", sam, "update messages set body='x' where bridge_id=%s", (bid,))
denied("cannot delete messages", sam, "delete from messages where bridge_id=%s", (bid,))
denied("outsider reads no chat", eve, "select * from messages where bridge_id=%s", (bid,))
denied("outsider cannot post", eve, "insert into messages (bridge_id,body) values (%s,'spam')", (bid,))

print("profiles / isolation")
run(paul, "insert into profiles (display_name, topics) values ('Paul', '{Politics}')")
check("own profile readable", run(paul, "select display_name from profiles") == [("Paul",)])
denied("other's profile not readable", sam, "select * from profiles where id=%s", (paul,))
denied("cannot create profile for someone else", mallory, "insert into profiles (id, display_name) values (%s,'x')", (sam,))
b2 = run(mallory, "select id from public.create_bridge('M','Other','https://x.y/z')")[0][0]
check("Paul lists only his bridges", [str(r[0]) for r in run(paul, "select id from bridges")] == [bid])
denied("Paul cannot see Mallory's bridge", paul, "select * from bridges where id=%s", (str(b2),))
check("owner can delete own bridge", run(mallory, "delete from bridges where id=%s", (str(b2),)) == 1)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
