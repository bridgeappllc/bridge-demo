"""DB tests for tips v2 earn-first (20261018090000_tips_earn_first.sql)."""
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
for u, nm in ((A, "a"), (B, "b"), (C, "c"), (X, "x")): confirm(u, f"{nm}-{tag}@test.local")
print("tip_accounts2 / live tables isolated")
adm("insert into tip_accounts2 (user_id, stripe_account_id, charges_enabled, payouts_enabled) values (%s,%s,true,true)", (C, "acct_s" + C.replace("-", "")[:12]))
check("owner reads own sandbox account", len(run(C, "select 1 from tip_accounts2")) == 1)
denied("others can't read it", A, "select * from tip_accounts2 where user_id=%s", (C,))
raises("users can't insert", B, "insert into tip_accounts2 (user_id, stripe_account_id) values (%s,'acct_x')", (B,))
check("live tips_enabled_for ignores sandbox accounts", run(A, "select tips_enabled_for(%s)", (C,)) == [(False,)])
print("tips2_can_tip")
check("anyone (not onboarded) can be tipped", run(A, "select tips2_can_tip(%s)", (B,)) == [(True,)])
check("not yourself", run(A, "select tips2_can_tip(%s)", (A,)) == [(False,)])
raises("anon can't call", None, "select tips2_can_tip(%s)", (A,))
# pod: A shares a bridge, B joins
bid_ = run(A, "select id from create_bridge(%s,%s,'https://example.org/x','Podcast','','','','')", (f"Ann{tag}", f"Clip {tag}"))[0][0]
tok = adm("select invite_token from bridges where id=%s", (bid_,))[0][0]; run(B, "select join_bridge(%s,%s)", (tok, f"Ben{tag}"))
print("tips2_prepare")
raises("authenticated can't call prepare", A, "select * from tips2_prepare(%s,%s,'thanks',null,null)", (A, B))
check("thank-you to non-onboarded: no destination", run("service", "select stripe_account_id from tips2_prepare(%s,%s,'thanks',null,null)", (A, B)) == [(None,)])
check("thank-you to onboarded: destination", run("service", "select stripe_account_id from tips2_prepare(%s,%s,'thanks',null,null)", (A, C))[0][0].startswith("acct_s"))
check("listen tip for a member who hasn't answered", run("service", "select title from tips2_prepare(%s,%s,'listen','bridge',%s)", (A, B, bid_)) == [(f"Clip {tag}",)])
raises("listen tip needs a clip", "service", "select * from tips2_prepare(%s,%s,'listen',null,null)", (A, B), "pick a clip")
raises("listen tip for a non-member", "service", "select * from tips2_prepare(%s,%s,'listen','bridge',%s)", (A, C, bid_), "isn't in this pod")
raises("tipper must be in the pod", "service", "select * from tips2_prepare(%s,%s,'listen','bridge',%s)", (X, B, bid_), "pod not found")
raises("self", "service", "select * from tips2_prepare(%s,%s,'thanks',null,null)", (A, A), "yourself")
run(B, "select block_user(%s)", (X,))
raises("blocked", "service", "select * from tips2_prepare(%s,%s,'thanks',null,null)", (X, B), "not found")
run(B, "select unblock_user(%s)", (X,))
print("held → earned on answer; notifications; RLS")
def tip(purpose, tipper, rec, kind=None, ref=None, mode="platform", acct=None):
    sid = "cs_t" + str(uuid.uuid4().int)[:12]
    adm("insert into tips2 (purpose, mode, tipper, recipient, tipper_name, title, pod_kind, pod_ref, amount_cents, fee_cents, total_cents, app_cut_cents, recipient_cents, application_fee_cents, stripe_account_id, checkout_session_id) values (%s,%s,%s,%s,'Ann',%s,%s,%s,500,46,546,50,450,%s,%s,%s)",
        (purpose, mode, tipper, rec, f"Clip {tag}", kind, ref, 96 if mode == "destination" else None, acct, sid)); return sid
s1 = tip("listen", A, B, "bridge", bid_)
check("tipper and recipient read it; others don't", len(run(A, "select 1 from tips2 where checkout_session_id=%s", (s1,))) == 1 and len(run(B, "select 1 from tips2 where checkout_session_id=%s", (s1,))) == 1)
denied("third party can't read", C, "select * from tips2 where checkout_session_id=%s", (s1,))
raises("users can't write tips2", A, "update tips2 set status='earned' where checkout_session_id=%s", (s1,)) if False else denied("users can't update tips2", A, "update tips2 set status='earned' where checkout_session_id=%s", (s1,))
raises("users can't mark paid", A, "select tips2_mark_paid(%s,'pi_x',false)", (s1,))
run("service", "select tips2_mark_paid(%s,'pi_1',false)", (s1,))
check("listen tip → held", adm("select status from tips2 where checkout_session_id=%s", (s1,)) == [("held",)])
check("tip_waiting notification", adm("select title from notifications where user_id=%s and kind='tip_waiting'", (B,))[0][0].startswith("$5 tip for listening to"))
check("mark_paid idempotent", run("service", "select tips2_mark_paid(%s,'pi_1',false)", (s1,)) == [(None,)])
run(B, "insert into answers (bridge_id, user_id, a1, a2, a3, rating) values (%s,%s,'x','x','an answer',7)", (bid_, B))
check("answering earns it", adm("select status, earned_at is not null from tips2 where checkout_session_id=%s", (s1,)) == [("earned", True)])
check("tip_earned notification", adm("select title from notifications where user_id=%s and kind='tip_earned'", (B,))[0][0].startswith("$5 for listening to"))
raises("no listen tip once answered", "service", "select * from tips2_prepare(%s,%s,'listen','bridge',%s)", (A, B, bid_), "already answered")
s2 = tip("thanks", A, C, mode="destination", acct="acct_s" + C.replace("-", "")[:12]); run("service", "select tips2_mark_paid(%s,'pi_2',false)", (s2,))
check("destination tip → paid_out", adm("select status from tips2 where checkout_session_id=%s", (s2,)) == [("paid_out",)])
s3 = tip("thanks", A, X); run("service", "select tips2_mark_paid(%s,'pi_3',false)", (s3,))
check("platform thank-you → earned + 'Set up payouts' notification", adm("select status from tips2 where checkout_session_id=%s", (s3,)) == [("earned",)] and adm("select title from notifications where user_id=%s and kind='tip'", (X,)) == [("$5. Set up payouts to collect it",)])
print("refundable + admin")
check("nothing refundable yet", not [r for r in run("service", "select checkout_session_id from tips2_refundable()") if r[0] in (s1, s3)])
adm("update tips2 set earned_at = now() - interval '91 days' where checkout_session_id=%s", (s3,))
check("earned 90+ days → refundable", any(r[0] == s3 for r in run("service", "select checkout_session_id from tips2_refundable()")))
raises("users can't list refundable", A, "select * from tips2_refundable()")
s4 = tip("listen", A, B, "group_clip", str(uuid.uuid4())); adm("update tips2 set status='held', paid_at=now(), payment_intent_id='pi_4' where checkout_session_id=%s", (s4,))
check("held tip whose clip is gone → refundable", any(r[0] == s4 for r in run("service", "select checkout_session_id from tips2_refundable()")))
raises("non-admin can't read admin_tip_stats2", A, "select admin_tip_stats2()")
adm("insert into stats_admins(email) values (%s) on conflict do nothing", (f"c-{tag}@test.local",))
st = run(C, "select admin_tip_stats2()")[0][0]
check(f"admin stats2 has held/owed/paid_out ({st})", all(k in st for k in ("held_cents", "owed_cents", "paid_out_cents", "refunded_cents")))
print(f"\n{passed} passed, {failed} failed"); raise SystemExit(1 if failed else 0)
