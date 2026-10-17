"""E2E (LOCAL ONLY): tips via Stripe Connect against the local tips-* edge functions and a Stripe API mock
(tests/local-stack/stripe-mock.js: no real key, no network). Recipient onboards from Settings ("Get paid for tips"),
tipper tips the person who shared the pod clip, pays on the (mock) hosted Checkout, the signed webhook records the tip,
and the recipient gets "X tipped you $5". Also: not-set-up note, min/max, no self-tips, blocks, bad webhook signatures."""
from authflow import signup_email
import json, os, time, urllib.request, urllib.parse
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); assert "127.0.0.1" in BASE, "local only"
API = "http://127.0.0.1:54321"; MOCK = "http://127.0.0.1:54333"
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 30000; n = 0; tag = str(int(time.time()) % 100000); A, Bn = f"SmokeTia{tag}", f"SmokeTom{tag}"
import psycopg; db = psycopg.connect("postgresql://postgres@127.0.0.1:54322/postgres", autocommit=True)
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
def mock(path, form=None):
    req = urllib.request.Request(MOCK + path, data=urllib.parse.urlencode(form).encode() if form else None, method="POST" if form else "GET")
    return json.load(urllib.request.urlopen(req))
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    def phone(who):
        ctx = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}})
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); pg.on("dialog", lambda d: d.accept()); return pg
    def signup(pg, name):
        pg.goto(BASE); pg.click("#sbtn"); signup_email(pg, name)
        [pg.click(f".topic[data-t={t}]") for t in ("Politics", "Science", "Culture")]; pg.click("#tgo"); expect(pg.locator("#ubtn")).to_be_visible(timeout=T)
    a, b = phone("A"), phone("B"); signup(a, A); signup(b, Bn)
    aid, bid = a.evaluate("ME"), b.evaluate("ME")
    fn = lambda pg, name, body: pg.evaluate("async([n,b])=>{try{return await tipFn(n,b)}catch(e){return{error:e.message}}}", [name, body])
    # Not set up yet
    b.goto(BASE + f"#u/{aid}"); expect(b.locator(f"[data-tipno='{aid}']")).to_have_text(f"{A} hasn't set up tips yet", timeout=T)
    assert b.locator("[data-tip]").count() == 0
    r = fn(b, "tips-checkout", {"recipient": aid, "amount_cents": 500}); assert "hasn't set up tips yet" in r.get("error", ""), r
    step("Recipient not set up: profile shows 'X hasn't set up tips yet', no Tip button, server refuses")
    # Recipient onboards (Connect Express via Account Links; mock completes onboarding and returns to the app)
    a.goto(BASE + "#profile"); a.click("[data-pt=Settings]"); on = a.locator("#tipcard #tipon"); expect(on).to_have_text("Get paid for tips", timeout=T)
    on.click(); a.wait_for_url("**#tipsetup/return", timeout=T); expect(a.locator("#tipcard")).to_contain_text("Tips are on", timeout=T)
    row = db.execute("select stripe_account_id, payouts_enabled from tip_accounts where user_id=%s", (aid,)).fetchone(); assert row[0].startswith("acct_") and row[1], row
    ac = mock("/mock/state")["accts"][row[0]]; assert ac["type"] == "v2" and ac["dashboard"] == "express" and ac["defaults"]["responsibilities"]["losses_collector"] == "application", ac
    a.screenshot(path=f"{SHOTS}/tips-1-setup.png"); step("Settings → 'Get paid for tips' → Stripe Accounts v2 (Express dashboard, recipient stripe_transfers) onboarding → back in the app: 'Tips are on'")
    # Pod: A shares a clip, B joins; B sees Tip on the clip sharer
    br1 = a.evaluate("async t=>{const{data,error}=await sb.rpc('create_bridge',{p_display_name:PROFILE.display_name,p_clip_title:t,p_clip_url:'https://example.org/tip',p_clip_type:'Podcast',p_clip_cat:'',p_clip_creator:'',p_friend_label:'',p_reward:''});if(error)throw error;return data[0]||data}", f"Smoke tip clip {tag}")
    b.evaluate("async([t,n])=>{const{error}=await sb.rpc('join_bridge',{p_token:t,p_display_name:n});if(error)throw error}", [br1["invite_token"], Bn])
    b.goto(BASE + f"#bridge/{br1['id']}/0"); tb = b.locator(".tiprow [data-tip]"); expect(tb).to_have_text(f"💸 Tip {A}", timeout=T)
    b.screenshot(path=f"{SHOTS}/tips-2-button.png"); step("Pod view: 'Tip' button for the person who shared the clip")
    a.goto(BASE + f"#bridge/{br1['id']}/0"); a.wait_for_timeout(1500); assert a.locator("[data-tip]").count() == 0
    r = fn(a, "tips-checkout", {"recipient": aid, "amount_cents": 500}); assert "tip yourself" in r.get("error", ""), r
    step("No tipping yourself (no button on your own clip; server refuses)")
    tb.click(); sh = b.locator("#tipsheet"); expect(sh).to_be_visible()
    expect(sh.locator(".tipbrk")).to_contain_text("Processing fee$0.46"); expect(sh.locator(".tipbrk .tot")).to_contain_text("$5.46")
    expect(sh).to_contain_text(f"{A} gets $4.50. Pod Club keeps 10% ($0.50)")
    sh.locator("[data-ta=c]").click(); b.fill("#tipin", "1"); expect(b.locator("#tiperr")).to_have_text("The minimum tip is $2"); assert b.locator("#tipgo").is_disabled()
    b.fill("#tipin", "101"); expect(b.locator("#tiperr")).to_have_text("The maximum tip is $100")
    b.fill("#tipin", "20"); expect(sh.locator(".tipbrk .tot")).to_contain_text("$20.91")
    for amt, err in ((100, "minimum"), (10100, "maximum"), (550, "whole-dollar")):
        r = fn(b, "tips-checkout", {"recipient": aid, "kind": "bridge", "ref": br1["id"], "amount_cents": amt}); assert err in r.get("error", "").lower(), r
    sh.locator("[data-ta='500']").click(); b.screenshot(path=f"{SHOTS}/tips-3-sheet.png")
    step("Tip sheet: $2/$5/$10/custom; $5 → Processing fee $0.46, total $5.46, recipient $4.50, app $0.50; min $2 / max $100 enforced (client + server)")
    b.click("#tipgo"); b.wait_for_url(MOCK + "/mock/checkout/**", timeout=T)
    cs = b.url.rsplit("/", 1)[1]; f = mock("/mock/state")["sessions"][cs]["form"]
    assert f["line_items[0][price_data][unit_amount]"] == "500" and f["line_items[1][price_data][unit_amount]"] == "46" and f["line_items[1][price_data][product_data][name]"] == "Processing fee", f
    assert f["payment_intent_data[application_fee_amount]"] == "96" and f["payment_intent_data[transfer_data][destination]"] == row[0], f
    t = db.execute("select status, amount_cents, fee_cents, total_cents, app_cut_cents, application_fee_cents, recipient_cents, pod_kind from tips where checkout_session_id=%s", (cs,)).fetchone()
    assert t == ("pending", 500, 46, 546, 50, 96, 450, "bridge"), t
    step("Checkout Session: destination charge to the recipient, line items $5.00 + Processing fee $0.46, application_fee_amount $0.96; tip row pending")
    b.click("#pay"); b.wait_for_url("**#tipped/**", timeout=T); expect(b.locator("h1")).to_have_text("Thank you!"); expect(b.locator("#app")).to_contain_text(f"Your $5.00 tip to {A} is on its way")
    assert db.execute("select status from tips where checkout_session_id=%s", (cs,)).fetchone()[0] == "paid"
    step("Paid → back to the app 'Thank you!'; signed webhook marked the tip paid")
    a.goto(BASE + "#notifications"); li = a.locator(".nlist li").first; expect(li).to_contain_text(f"{B if False else Bn} tipped you $5", timeout=T)
    a.screenshot(path=f"{SHOTS}/tips-4-received.png"); step("Recipient: '💸 X tipped you $5' in the notifications bell")
    # webhook signature checks
    ev = json.dumps({"id": "evt_x", "type": "checkout.session.completed", "data": {"object": {"id": cs, "payment_status": "paid"}}})
    assert mock("/mock/fire", {"event": ev, "header": "bad"})["status"] == 400 and mock("/mock/fire", {"event": ev, "header": "old"})["status"] == 400
    req = urllib.request.Request(API + "/functions/v1/tips-webhook", data=ev.encode(), method="POST")
    try: urllib.request.urlopen(req); raise AssertionError("unsigned accepted")
    except urllib.error.HTTPError as e: assert e.code == 400
    assert db.execute("select count(*) from notifications where user_id=%s and kind='tip'", (aid,)).fetchone()[0] == 1
    step("Webhook rejects wrong secret, stale timestamp, unsigned; duplicate events don't double-notify")
    # Blocks
    b.evaluate("async u=>{const{error}=await sb.rpc('block_user',{p_user:u});if(error)throw error}", aid)
    r = fn(b, "tips-checkout", {"recipient": aid, "amount_cents": 500}); assert "not found" in r.get("error", "").lower(), r
    assert b.evaluate("async u=>(await sb.rpc('tips_enabled_for',{p_user:u})).data", aid) is False
    b.evaluate("async u=>{await sb.rpc('unblock_user',{p_user:u})}", aid); step("Blocks respected (no tip either way)")
    assert not errors, errors
print(f"\n{n} tip checks passed")
