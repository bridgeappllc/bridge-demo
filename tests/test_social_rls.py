"""DB rule tests for the social migration (profiles/@usernames, friends, blocks,
library visibility). Same harness as test_rls.py: each user is simulated the way
PostgREST does it (SET ROLE authenticated + request.jwt.claims)."""
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
lib = lambda viewer, owner: len(run(viewer, "select id from library_items where user_id=%s", (owner,)))
status = lambda me, other: run(me, "select friend_status from get_profile(%s)", (other,))[0][0]
for i in (1, 2): run(A, "insert into library_items (user_id,url,title,category) values (%s,%s,%s,'Science')", (A, f"https://example.org/a{i}-{tag}", f"A item {i}"))

print("profiles + usernames")
check("new columns have defaults (bio '', visibility friends, no username)", run(A, "select username, bio, library_visibility from profiles where id=%s", (A,)) == [(None, "", "friends")])
check("set own @username", run(A, "update profiles set username=%s where id=%s", (f"alice_{tag}", A)) == 1)
raises("username too short rejected", B, "update profiles set username='ab' where id=%s", (B,), "username_format")
raises("username with capitals/spaces rejected", B, "update profiles set username='Bob X' where id=%s", (B,), "username_format")
raises("duplicate username rejected", B, "update profiles set username=%s where id=%s", (f"alice_{tag}", B), "duplicate")
raises("reserved username rejected (admin)", B, "update profiles set username='admin' where id=%s", (B,), "not_reserved")
raises("reserved username rejected (bridge)", B, "update profiles set username='bridge' where id=%s", (B,), "not_reserved")
raises("reserved username rejected (meetonthebridge)", B, "update profiles set username='meetonthebridge' where id=%s", (B,), "not_reserved")
check("reserved names report unavailable; 'paul' style names allowed", run(B, "select username_available('support'), username_available('clipclub'), username_available(%s)", (f"paul{tag}",)) == [(False, False, True)])
check("username_available: taken -> false, free -> true", run(B, "select username_available(%s), username_available(%s)", (f"alice_{tag}", f"bob_{tag}")) == [(False, True)])
check("bio up to 160 chars", run(A, "update profiles set bio='Podcasts about science and cities.' where id=%s", (A,)) == 1)
raises("bio over 160 chars rejected", A, "update profiles set bio=%s where id=%s", ("x" * 161, A), "bio_length")
raises("invalid visibility value rejected", A, "update profiles set library_visibility='public' where id=%s", (A,), "library_visibility")
denied("cannot edit someone else's profile", B, "update profiles set display_name='hacked', username='hacked' where id=%s", (A,))
denied("other people's profile rows are not directly readable (topics etc. stay private)", B, "select * from profiles where id=%s", (A,))
r = run(B, "select id, display_name, username, bio, friend_status from search_people('ali')")
check("search by name finds Alice (basics only)", any(str(x[0]) == A and x[2] == f"alice_{tag}" and x[4] == "none" for x in r))
check("search by @username works", any(str(x[0]) == A for x in run(B, "select * from search_people(%s)", (f"@alice_{tag}",))))
check("search ignores 1-char queries", run(B, "select * from search_people('a')") == [])
check("search doesn't treat % / _ as wildcards", run(B, "select * from search_people('%%')") == [] and run(B, "select * from search_people('__')") == [])
check("search never returns yourself", all(str(x[0]) != A for x in run(A, "select * from search_people(%s)", (f"alice{tag}",))))
p = run(B, "select display_name, username, bio, friend_status, library_count, can_view_library, library_visibility from get_profile(%s)", (A,))
check("get_profile by id: basics, but library hidden from a stranger", p == [(f"Alice{tag}", f"alice_{tag}", "Podcasts about science and cities.", "none", None, False, "friends")])
check("get_profile by @username", str(run(B, "select id from get_profile(null, %s)", (f"@alice_{tag}",))[0][0]) == A)
denied("anon (no session) cannot search", None, "select * from search_people('alice')")
denied("anon cannot get a profile", None, "select * from get_profile(%s)", (A,))

print("library visibility: default 'friends'")
check("owner sees own library", lib(A, A) == 2)
check("stranger cannot see library (default)", lib(B, A) == 0)
bid = str(run(A, "select id from create_bridge('Alice','T','https://example.org/t')")[0][0]); tok = run(A, "select invite_token from bridges where id=%s", (bid,))[0][0]
run(D, "select join_bridge(%s,'Dave')", (tok,))
check("bridge partner still sees library (old rule kept under 'friends')", lib(D, A) == 2)

print("friend requests")
raises("cannot friend yourself", A, "select send_friend_request(%s)", (A,), "yourself")
raises("cannot friend a nonexistent user", A, "select send_friend_request(%s)", (str(uuid.uuid4()),), "not found")
denied("cannot insert a friendship directly", B, "insert into friendships (requester, addressee, status) values (%s,%s,'accepted')", (B, A))
check("B sends request -> outgoing", run(B, "select send_friend_request(%s)", (A,)) == [("outgoing",)])
check("sending twice is idempotent", run(B, "select send_friend_request(%s)", (A,)) == [("outgoing",)])
check("A sees it as incoming (my_requests + status)", status(A, B) == "incoming" and any(str(x[0]) == B and x[3] == "incoming" for x in run(A, "select * from my_requests()")))
denied("cannot accept by updating the row directly", B, "update friendships set status='accepted' where requester=%s", (B,))
check("requester cannot accept their own request", run(B, "select respond_friend_request(%s, true)", (A,)) == [("outgoing",)])
check("pending request does not unlock the library", lib(B, A) == 0)
denied("third person cannot see A–B request rows", C, "select * from friendships where requester=%s or addressee=%s", (B, B))
check("A accepts -> friends", run(A, "select respond_friend_request(%s, true)", (B,)) == [("friends",)] and status(B, A) == "friends")
check("friend sees full library", lib(B, A) == 2)
check("get_profile shows library count to friend", run(B, "select library_count, can_view_library, friends_count from get_profile(%s)", (A,)) == [(2, True, 1)])
check("friends_of(A) visible to A's friend B", any(str(x[0]) == B for x in run(B, "select * from friends_of(%s)", (A,))))
check("friends_of(A) hidden from non-friend C", run(C, "select * from friends_of(%s)", (A,)) == [])
check("mutual requests auto-accept", run(C, "select send_friend_request(%s)", (A,)) == [("outgoing",)] and run(A, "select send_friend_request(%s)", (C,)) == [("friends",)])
run(E, "select send_friend_request(%s)", (A,))
check("decline removes the request", run(A, "select respond_friend_request(%s, false)", (E,)) == [("none",)] and status(E, A) == "none")
run(E, "select send_friend_request(%s)", (C,))
check("cancel own outgoing request", run(E, "select remove_friend(%s)", (C,)) == [("none",)] and status(C, E) == "none")
check("suggest_people lists bridge partner who isn't a friend", any(str(x[0]) == D for x in run(A, "select * from suggest_people()")) and all(str(x[0]) != B for x in run(A, "select * from suggest_people()")))

print("privacy levels")
run(A, "update profiles set library_visibility='private' where id=%s", (A,))
check("'Only me': friend cannot see", lib(B, A) == 0)
check("'Only me': bridge partner cannot see", lib(D, A) == 0)
check("'Only me': owner still sees", lib(A, A) == 2)
check("'Only me': profile says hidden", run(B, "select library_count, can_view_library from get_profile(%s)", (A,)) == [(None, False)])
run(A, "update profiles set library_visibility='everyone' where id=%s", (A,))
check("'Everyone': stranger (signed in) sees", lib(E, A) == 2)
denied("'Everyone': still nothing for anon (no session)", None, "select * from library_items where user_id=%s", (A,))
denied("cannot change someone else's visibility", E, "update profiles set library_visibility='everyone' where id=%s", (B,))
denied("cannot add to someone else's library", B, "insert into library_items (user_id,url,title) values (%s,'https://x.y/z','t')", (A,))
run(A, "update profiles set library_visibility='friends' where id=%s", (A,))
check("back to 'Friends only': stranger blocked, friend + partner allowed", lib(E, A) == 0 and lib(B, A) == 2 and lib(D, A) == 2)

print("unfriend / block")
check("unfriend", run(B, "select remove_friend(%s)", (A,)) == [("none",)] and status(A, B) == "none")
check("after unfriending, library hidden again", lib(B, A) == 0)
run(A, "update profiles set library_visibility='everyone' where id=%s", (A,))
run(E, "select block_user(%s)", (A,))
check("blocker no longer finds the person in search", all(str(x[0]) != A for x in run(E, "select * from search_people('alice')")))
check("blocked person can't find the blocker either", all(str(x[0]) != E for x in run(A, "select * from search_people('eve')")))
check("block hides profile both ways", run(A, "select * from get_profile(%s)", (E,)) == [] and run(E, "select * from get_profile(%s)", (A,)) == [])
check("block hides library even when set to Everyone", lib(E, A) == 0)
raises("blocked person cannot send a request", A, "select send_friend_request(%s)", (E,), "not found")
check("my_blocks lists them; others can't read my blocks", any(str(x[0]) == A for x in run(E, "select * from my_blocks()")) and run(A, "select * from blocks") == [])
run(C, "select block_user(%s)", (A,))
check("blocking a friend removes the friendship (and hides the profile)", run(A, "select * from friendships where %s in (requester, addressee)", (C,)) == [] and run(A, "select * from get_profile(%s)", (C,)) == [])
run(C, "select unblock_user(%s)", (A,)); run(E, "select unblock_user(%s)", (A,))
check("unblock restores visibility (Everyone)", lib(E, A) == 2 and status(C, A) == "none")
run(A, "update profiles set library_visibility='friends' where id=%s", (A,))

print("start a bridge directly with a friend")
run(B, "select send_friend_request(%s)", (A,)); run(A, "select respond_friend_request(%s, true)", (B,))
b2 = str(run(A, "select id from create_bridge('Alice','Fav','https://example.org/a1-x')")[0][0])
raises("non-owner cannot add people to a bridge", B, "select add_friend_to_bridge(%s,%s)", (b2, B), "not found")
raises("owner cannot add a non-friend", A, "select add_friend_to_bridge(%s,%s)", (b2, E), "only add friends")
run(A, "select add_friend_to_bridge(%s,%s)", (b2, B))
check("owner adds a friend -> friend is a member and sees the bridge", len(run(B, "select * from bridges where id=%s", (b2,))) == 1 and run(B, "select role, display_name from bridge_members where bridge_id=%s and user_id=%s", (b2, B)) == [("friend", f"Bob{tag}")])
run(D, "select send_friend_request(%s)", (A,)); run(A, "select respond_friend_request(%s, true)", (D,))
raises("bridge with two people cannot take a third", A, "select add_friend_to_bridge(%s,%s)", (b2, D), "two people")
check("existing flow intact: friend can answer the bridge", run(B, "insert into answers (bridge_id,user_id,a1,a2,a3) values (%s,%s,'x1','x2','x3')", (b2, B)) == 1)

print("API surface")
for f in ("search_people('x')", "get_profile(null,'x')", "friends_of(gen_random_uuid())", "my_requests()", "suggest_people()", "my_blocks()", "username_available('abc')", "send_friend_request(gen_random_uuid())", "remove_friend(gen_random_uuid())", "block_user(gen_random_uuid())", "add_friend_to_bridge(gen_random_uuid(),gen_random_uuid())"):
    denied(f"anon cannot call {f.split('(')[0]}", None, f"select * from {f}")
denied("private helpers not callable by anon", None, "select private.can_view_library(gen_random_uuid())")
denied("anon cannot read friendships", None, "select * from friendships")
print(f"\n{passed} passed, {failed} failed"); raise SystemExit(1 if failed else 0)
