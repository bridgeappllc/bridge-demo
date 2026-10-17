"""DB tests for tips (20261017090000_tips.sql): owner-only reads, tip_prepare rules (self, blocks, set-up, pod sharer), webhook marking + notification, admin totals."""
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
adm = lambda sql, p=(): (lambda c: c.fetchall() if c.description else c.rowcount)(conn.execute(sql, p))
tag = str(uuid.uuid4().int)[:6]  # digits only: random hex can trip the name filter
def confirm(u, email): conn.execute("update auth.users set email=%s, email_confirmed_at=now(), is_anonymous=false where id=%s", (email, u))
A, B, C, X = (new_user(n) for n in (f"Ann{tag}", f"Ben{tag}", f"Cat{tag}", f"Xan{tag}"))
for u, n in ((A, "a"), (B, "b"), (C, "c"), (X, "x")): confirm(u, f"{n}-{tag}@test.local")
acct = lambda u, ready: adm("insert into tip_accounts (user_id, stripe_account_id, details_submitted, charges_enabled, payouts_enabled) values (%s,%s,%s,%s,%s) on conflict (user_id) do update set charges_enabled=excluded.charges_enabled, payouts_enabled=excluded.payouts_enabled returning user_id", (u, "acct_t" + u.replace("-", "")[:12], ready, ready, ready))
acct(A, True); acct(C, False)
print("tip_accounts")
check("owner reads own account", len(run(A, "select stripe_account_id from tip_accounts")) == 1)
denied("others can't read someone's account", B, "select * from tip_accounts where user_id=%s", (A,))
denied("anon can't read accounts", None, "select * from tip_accounts")
raises("users can't insert accounts", B, "insert into tip_accounts (user_id, stripe_account_id) values (%s,'acct_x')", (B,))
raises("users can't flip payouts on", C, "update tip_accounts set payouts_enabled=true where user_id=%s", (C,))
print("tips_enabled_for")
check("B sees A can get tips", run(B, "select tips_enabled_for(%s)", (A,)) == [(True,)])
check("not set up -> false", run(B, "select tips_enabled_for(%s)", (C,)) == [(False,)])
check("self -> false", run(A, "select tips_enabled_for(%s)", (A,)) == [(False,)])
raises("anon can't call", None, "select tips_enabled_for(%s)", (A,))
print("tip_prepare")
prep = lambda t, r, k=None, ref=None: run("service", "select stripe_account_id, recipient_name, tipper_name, title from tip_prepare(%s,%s,%s,%s)", (t, r, k, ref))
check("profile tip ok", prep(B, A)[0][1] == f"Ann{tag}")
raises("no tipping yourself", "service", "select * from tip_prepare(%s,%s,null,null)", (A, A), "tip yourself")
raises("not set up", "service", "select * from tip_prepare(%s,%s,null,null)", (B, C), "hasn't set up tips")
raises("clients can't call tip_prepare", B, "select * from tip_prepare(%s,%s,null,null)", (B, A))
b = run(A, "select id from create_bridge(%s,'Tip me','https://example.org/tip')", (f"Ann{tag}",))[0]; bid = str(b[0])
raises("non-member can't tip on a pod", "service", "select * from tip_prepare(%s,%s,'bridge',%s)", (X, A, bid), "pod not found")
adm("insert into bridge_members (bridge_id, user_id, display_name, role) values (%s,%s,%s,'friend')", (bid, B, f"Ben{tag}"))
check("member tips the sharer on a pod", prep(B, A, "bridge", bid)[0][3] == "Tip me")
raises("pod tip must go to whoever shared it", "service", "select * from tip_prepare(%s,%s,'bridge',%s)", (A, B, bid), "")
g = run(A, "select create_group_pod('Tippers', %s)", ([B],))[0][0]
gc = run(A, "select share_to_group_pod(%s,'Group clip','https://example.org/g','Article','')", (g,))[0][0]
check("group member tips the clip sharer", prep(B, A, "group_clip", str(gc))[0][3] == "Group clip")
raises("group non-member can't", "service", "select * from tip_prepare(%s,%s,'group_clip',%s)", (X, A, str(gc)), "pod not found")
run(B, "select block_user(%s)", (A,))
raises("blocked -> not found", "service", "select * from tip_prepare(%s,%s,null,null)", (B, A), "not found")
check("blocked -> tips_enabled_for false", run(B, "select tips_enabled_for(%s)", (A,)) == [(False,)])
check("blocked the other way too", run(A, "select tips_enabled_for(%s)", (B,)) == [(False,)])
run(B, "select unblock_user(%s)", (A,))
print("tips + webhook")
sess = f"cs_test_{tag}"
ins = "insert into tips (tipper, recipient, tipper_name, pod_kind, pod_ref, amount_cents, fee_cents, total_cents, app_cut_cents, application_fee_cents, recipient_cents, stripe_account_id, checkout_session_id) values (%s,%s,%s,'bridge',%s,500,46,546,50,96,450,'acct_x',%s)"
raises("users can't insert tips", B, ins, (B, A, "Ben", bid, sess + "u"))
raises("amounts must add up", "service", ins.replace("450,'acct_x'", "460,'acct_x'"), (B, A, f"Ben{tag}", bid, sess + "bad"))
raises("minimum $2", "service", ins.replace("500,46,546", "100,46,146"), (B, A, f"Ben{tag}", bid, sess + "min"))
run("service", ins, (B, A, f"Ben{tag}", bid, sess))
check("tipper reads own tip", len(run(B, "select id from tips where checkout_session_id=%s", (sess,))) == 1)
check("recipient reads it", len(run(A, "select id from tips where checkout_session_id=%s", (sess,))) == 1)
denied("third party can't", X, "select id from tips where checkout_session_id=%s", (sess,))
raises("clients can't mark paid", B, "select tip_mark_paid(%s,'pi_x',false)", (sess,))
check("webhook marks paid", run("service", "select tip_mark_paid(%s,'pi_x',false)", (sess,))[0][0] is not None)
check("idempotent (second event ignored)", run("service", "select tip_mark_paid(%s,'pi_x',false)", (sess,)) == [(None,)])
n = run(A, "select kind, actor_name, title, bridge_id from notifications where kind='tip'")
check(f"recipient notified 'Ben tipped you $5': {n}", n == [("tip", f"Ben{tag}", "$5", uuid.UUID(bid))])
check("status paid", run(B, "select status from tips where checkout_session_id=%s", (sess,)) == [("paid",)])
run(A, "select block_user(%s)", (B,))
run("service", ins, (B, A, f"Ben{tag}", bid, sess + "2")); run("service", "select tip_mark_paid(%s,'pi_y',false)", (sess + "2",))
check("no notification from someone you blocked", len(run(A, "select id from notifications where kind='tip'")) == 1)
run(A, "select unblock_user(%s)", (B,))
print("admin_tip_stats")
raises("non-admin can't read tip stats", B, "select admin_tip_stats()", (), "not allowed")
adm("insert into stats_admins(email) values (%s) on conflict do nothing", (f"c-{tag}@test.local",))
st = run(C, "select admin_tip_stats()")[0][0]
check(f"admin sees totals {st}", st["tips"] >= 2 and st["tipped_cents"] >= 1000 and st["app_cut_cents"] >= 100)
adm("delete from stats_admins where email=%s", (f"c-{tag}@test.local",))
print(f"\n{passed} passed, {failed} failed"); raise SystemExit(1 if failed else 0)
