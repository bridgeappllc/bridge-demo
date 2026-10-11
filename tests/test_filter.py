"""DB tests for the content filter (supabase/migrations/20261011180000_content_filter.sql)
+ parity check: the client copy in index.html (MOD.norm/MOD.scan) must give the same verdicts as the DB."""
import json, os, re, random, shutil, subprocess, uuid, psycopg
DSN = os.environ.get("DSN", "postgresql://postgres@127.0.0.1:54322/postgres")
conn = psycopg.connect(DSN, autocommit=True)
passed = failed = 0
RESPECT = "Please keep it respectful"
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
def allowed(name, uid, sql, params=()):
    try: run(uid, sql, params); check(name, True)
    except psycopg.Error as e: check(f"{name} -> unexpected error: {str(e).splitlines()[0][:90]}", False)
def blocked(name, uid, sql, params=()):
    try: r = run(uid, sql, params); check(f"{name} -> unexpectedly allowed: {r}", False)
    except psycopg.Error as e:
        check(f"{name} (blocked: {e.sqlstate} {str(e).splitlines()[0][:40]})", e.sqlstate == "23514" and RESPECT in str(e))
def denied(name, uid, sql, params=()):
    try: r = run(uid, sql, params); check(f"{name} -> unexpectedly allowed: {r}", r == 0 or r == [])
    except psycopg.Error as e: check(f"{name} (error: {str(e).splitlines()[0][:60]})", True)
adm = lambda sql, p=(): conn.execute(sql, p).fetchall()

tag = uuid.uuid4().hex[:6]
A, B = new_user(f"Ann{tag}"), new_user(f"Ben{tag}")
L = new_user(None)  # 'legacy' user created below with content that predates the filter

print("names, @usernames, bios: anything on the list is blocked")
blocked("display name with a slur", A, "update profiles set display_name='N1gg3r lover' where id=%s", (A,))
blocked("display name with profanity", A, "update profiles set display_name='Shit Head' where id=%s", (A,))
blocked("display name with leetspeak profanity", A, "update profiles set display_name='b!tch' where id=%s", (A,))
allowed("Scunthorpe-style name is fine (Scunthorpe Cockburn)", A, "update profiles set display_name='Scunthorpe Cockburn' where id=%s", (A,))
blocked("new profile (insert) with profanity", new_user(None), "insert into profiles (id, display_name) values (auth.uid(), 'fuckface')")
blocked("@username with profanity (big_fuck_99)", A, "update profiles set username='big_fuck_99' where id=%s", (A,))
blocked("@username with a slur after leetspeak (f4gg0t)", A, "update profiles set username='f4gg0t' where id=%s", (A,))
allowed("@username classic_assassin is fine", A, "update profiles set username=%s where id=%s", (f"classic_ass{tag}"[:3]+f"assin{tag}", A))
blocked("bio with profanity", A, "update profiles set bio='I talk shit about podcasts' where id=%s", (A,))
blocked("bio with hate phrase (kill yourself)", A, "update profiles set bio='just kill   yourself' where id=%s", (A,))
allowed("bio 'Essex, cocktails, shiitake, Dickens' is fine", A, "update profiles set bio='Essex, cocktails, shiitake, Dickens, summa cum laude' where id=%s", (A,))
check("blocked updates changed nothing", adm("select display_name from profiles where id=%s", (A,))[0][0] == "Scunthorpe Cockburn")

print("chat: slurs blocked, profanity masked")
b = run(A, "select id, invite_token from create_bridge(%s,%s,%s)", ("Scunthorpe Cockburn", "Filter test", f"https://example.org/f-{tag}"))[0]
bid, tok = str(b[0]), b[1]
blocked("joining with a profane display name", B, "select join_bridge(%s,%s)", (tok, "Dickhead"))
allowed("joining with a clean name", B, "select join_bridge(%s,%s)", (tok, f"Ben{tag}"))
blocked("answers containing a slur", A, "insert into answers (bridge_id,user_id,a1,a2,a3) values (%s,auth.uid(),'fine','you are a kike','ok')", (bid,))
allowed("answers with profanity are accepted", A, "insert into answers (bridge_id,user_id,a1,a2,a3) values (%s,auth.uid(),'That was fucking great','ok then','bullshit, honestly')", (bid,))
check("answers were masked", adm("select a1, a3 from answers where bridge_id=%s and user_id=%s", (bid, A))[0] == ("That was f****** great", "b*******, honestly"))
run(B, "insert into answers (bridge_id,user_id,a1,a2,a3) values (%s,auth.uid(),'x1','y1','z1')", (bid,))
def say(uid, t):
    run(uid, "insert into messages (bridge_id,user_id,body) values (%s,auth.uid(),%s)", (bid, t))
    return adm("select body from messages where bridge_id=%s and user_id=%s order by id desc limit 1", (bid, uid))[0][0]
check("profanity masked: 'What the fuck!' -> 'What the f***!'", say(A, "What the fuck!") == "What the f***!")
check("leetspeak masked: 'sh!t, a55hole and $hit' ", say(A, "sh!t, a55hole and $hit") == "s***, a****** and $***")
check("stretched letters masked: 'fuuuuuck'", say(A, "fuuuuuck") == "f*******")
check("Scunthorpe problem avoided (unchanged)", say(A, "Scunthorpe, classic cocktails, an assassin, Sussex grass, therapist, cocky") == "Scunthorpe, classic cocktails, an assassin, Sussex grass, therapist, cocky")
check("self-censored text left alone (f*ck)", say(B, "f*ck that") == "f*ck that")
blocked("chat slur blocked", B, "insert into messages (bridge_id,user_id,body) values (%s,auth.uid(),'shut up you f@ggot')", (bid,))
blocked("chat 'kys' blocked", B, "insert into messages (bridge_id,user_id,body) values (%s,auth.uid(),'kys')", (bid,))
check("blocked messages were not stored", adm("select count(*) from messages where bridge_id=%s and user_id=%s", (bid, B))[0][0] == 1)

print("library: titles/notes/creators masked, slurs blocked")
run(A, "insert into library_items (user_id,url,title,note,creator) values (auth.uid(),%s,'Holy shit, what a show','This bitch of a week','The Fuckups')", (f"https://example.org/l1-{tag}",))
check("library title/note/creator masked", adm("select title, note, creator from library_items where url=%s", (f"https://example.org/l1-{tag}",))[0] == ("Holy s***, what a show", "This b**** of a week", "The F******"))
blocked("library note with a slur", A, "insert into library_items (user_id,url,title,note) values (auth.uid(),%s,'ok','go back home wetback')", (f"https://example.org/l2-{tag}",))
lid = adm("select id from library_items where url=%s", (f"https://example.org/l1-{tag}",))[0][0]
allowed("editing the note to clean text", A, "update library_items set note='Better now' where id=%s", (lid,))

print("existing content is never rewritten or blocking")
conn.execute("set session_replication_role = replica")   # simulate rows that existed before the filter (triggers off)
conn.execute("insert into profiles (id, display_name, bio) values (%s, 'Old Shit Name', 'old bio with bullshit')", (L,))
conn.execute("set session_replication_role = origin")
allowed("legacy user can update other columns (topics, library_visibility)", L, "update profiles set topics='{Science}', library_visibility='private' where id=%s", (L,))
check("legacy name/bio left exactly as they were", adm("select display_name, bio from profiles where id=%s", (L,))[0] == ("Old Shit Name", "old bio with bullshit"))
blocked("…but changing the bio to another profane bio is blocked", L, "update profiles set bio='still bullshit' where id=%s", (L,))
rows = adm("select field, verdict from private.content_filter_existing_matches where row_id=%s", (L,))
check(f"admin report view lists legacy matches {sorted(rows)}", sorted(rows) == [("profiles.bio", "profanity"), ("profiles.display_name", "profanity")])

print("word list access")
denied("clients can't read moderation_terms", A, "select * from moderation_terms")
denied("anon can't read moderation_terms", None, "select * from moderation_terms")
denied("clients can't add terms", A, "insert into moderation_terms (term, category) values ('zzz','profanity')")
denied("clients can't delete terms", A, "delete from moderation_terms where term='fuck'")
denied("clients can't read the admin report view", A, "select * from private.content_filter_existing_matches")
n_terms = adm("select count(*) from moderation_terms")[0][0]
check(f"anon + signed-in can fetch the pattern list for inline checks ({n_terms} terms)", len(run(None, "select * from moderation_terms_list()")) == n_terms == len(run(A, "select * from moderation_terms_list()")))
conn.execute("delete from moderation_terms where term in ('zqxbadword','two words')"); conn.execute("insert into moderation_terms (term, category, match) values ('zqxbadword','hate','stem')")
blocked("a term Paul adds takes effect immediately", A, "insert into messages (bridge_id,user_id,body) values (%s,auth.uid(),'zqxbadwords everywhere')", (bid,))
conn.execute("delete from moderation_terms where term='zqxbadword'")
allowed("…and removing it lifts the block", A, "insert into messages (bridge_id,user_id,body) values (%s,auth.uid(),'zqxbadwords everywhere')", (bid,))
try: conn.execute("insert into moderation_terms (term, category) values ('two words','profanity')"); check("multi-word profanity rejected", False)
except psycopg.Error: check("multi-word profanity is rejected (phrases can only be 'hate')", True)

print("client parity: index.html MOD.norm/MOD.scan == DB")
node = os.environ.get("NODE") or shutil.which("node") or "/workspace/bridge-mobile/tools/node22/bin/node"
html = open(os.path.join(os.path.dirname(__file__), "..", "index.html")).read()
m = re.search(r"const MOD=\{t:null,.*?\n scan\(s\)\{.*?\}\};", html, re.S)
check("found MOD in index.html", bool(m))
words = [w.strip() for w in open("/usr/share/dict/words")] if os.path.exists("/usr/share/dict/words") else []
random.seed(7); sample = random.sample(words, min(3000, len(words)))
crafted = ["What the fuck!", "sh!t happens", "a55hole", "$hit", "N1GG3R", "f4gg0t", "k y s", "kys loser", "kill   yourself", "p0rch m0nkey",
           "Scunthorpe", "spicy", "Fagin", "retarding", "cocky", "cock", "pussycat", "big_fuck_99", "fuuuuck", "b|tch", "Ass!", "classic", "a.s.s",
           "@ss", "5h1tty", "wank3r", "héllo shit", "ＦＵＣＫ", "f*ck", "", "   "] + [w + "s" for w in sample[:300]] + [w.upper() for w in sample[300:400]]
texts = crafted + sample
db = [r[0] for r in adm("select private.mod_scan(t) from unnest(%s::text[]) with ordinality u(t, i) order by i", (texts,))]
pats = [[r[0], r[1]] for r in adm("select category, pattern from moderation_terms")]
js = m.group(0) + "\nconst [rows,texts]=JSON.parse(require('fs').readFileSync(0,'utf8'));MOD.set(rows.map(([category,pattern])=>({category,pattern})));process.stdout.write(JSON.stringify(texts.map(t=>MOD.scan(t))));"
out = subprocess.run([node, "-e", js], input=json.dumps([pats, texts]), capture_output=True, text=True)
cl = json.loads(out.stdout or "null") if out.returncode == 0 else None
diff = [(t, d, c) for t, d, c in zip(texts, db, cl or [])] if cl else []
diff = [x for x in diff if x[1] != x[2]]
check(f"client and DB agree on {len(texts)} texts (diffs: {diff[:5]}) {out.stderr[:200]}", cl is not None and not diff)
check(f"spot-check verdicts DB={db[:6]}", db[:6] == ["profanity", "profanity", "profanity", "profanity", "hate", "hate"])

# cleanup (local stack only)
for u in (A, B, L): conn.execute("delete from auth.users where id=%s", (u,))
conn.execute("delete from auth.users where id in (select id from auth.users u where not exists (select 1 from profiles p where p.id=u.id) and u.created_at > now() - interval '5 minutes' and u.is_anonymous)")
print(f"{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
