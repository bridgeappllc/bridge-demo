"""E2E (LOCAL ONLY): tips v2 "earn first" + tips for listening, against the local tips2-* functions and the Stripe mock.
Tip anyone (no set-up needed) · listening tip added when sharing a clip (platform charge, held) · '$5 tip waiting' on the
pod · answering earns it · Settings 'You've earned $4.50 in tips. Get paid' · onboarding → idempotent Transfer with
source_transaction · onboarded recipients keep destination charges · not-onboarded thank-you tips are earned on payment ·
30/90-day refund sweep (cron secret) · self/blocks/already-answered refusals · live tips-checkout unchanged."""
from authflow import signup_email
import json, os, time, urllib.request, urllib.parse
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); assert "127.0.0.1" in BASE, "local only"
API = "http://127.0.0.1:54321"; MOCK = "http://127.0.0.1:54333"
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 30000; n = 0; tag = str(int(time.time()) % 100000); A, Bn, Cn = f"SmokeTia{tag}", f"SmokeTom{tag}", f"SmokeTed{tag}"
import psycopg; db = psycopg.connect("postgresql://postgres@127.0.0.1:54322/postgres", autocommit=True)
q1 = lambda sql, p=(): db.execute(sql, p).fetchone()
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
def mock(path, form=None):
    req = urllib.request.Request(MOCK + path, data=urllib.parse.urlencode(form).encode() if form else None, method="POST" if form else "GET")
    return json.load(urllib.request.urlopen(req))
def sweep(secret="cron_local_mock"):
    req = urllib.request.Request(API + "/functions/v1/tips2-payout", data=b"{}", method="POST", headers={"x-tips2-cron": secret})
    try: r = urllib.request.urlopen(req); return r.status, json.load(r)
    except urllib.error.HTTPError as e: return e.code, None
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    def phone(who):
        ctx = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}})
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); pg.on("dialog", lambda d: d.accept()); return pg
    def signup(pg, name):
        pg.goto(BASE); pg.click("#sbtn"); signup_email(pg, name)
        [pg.click(f".topic[data-t={t}]") for t in ("Politics", "Science", "Culture")]; pg.click("#tgo"); expect(pg.locator("#ubtn")).to_be_visible(timeout=T)
    a, b, c = phone("A"), phone("B"), phone("C"); signup(a, A); signup(b, Bn); signup(c, Cn)
    aid, bid, cid = a.evaluate("ME"), b.evaluate("ME"), c.evaluate("ME")
    fn = lambda pg, name, body: pg.evaluate("async([n,b])=>{try{return await tipFn(n,b)}catch(e){return{error:e.message}}}", [name, body])
    ev = lambda pg, js, arg=None: pg.evaluate(js, arg)
    LEGACY = "http://127.0.0.1:8080/legacy/"  # an app NOT in TIPS_INVITE_ONLY_APPS (like live today): thank-you tips still work
    fnL = lambda pg, name, body: pg.evaluate("async([n,b])=>{const{data}=await sb.auth.getSession();const r=await fetch(CFG.SUPABASE_URL+'/functions/v1/'+n,{method:'POST',headers:{Authorization:'Bearer '+data.session.access_token,apikey:CFG.SUPABASE_ANON_KEY,'Content-Type':'application/json'},body:JSON.stringify(b)});const j=await r.json().catch(()=>({}));return r.ok?j:{error:j.error||'error'}}", [name, {**body, "app": LEGACY}])
    # No standalone tipping: no Tip button on B's profile; tips2-checkout (invite-only app) rejects tips without a clip
    a.goto(BASE + f"#u/{bid}"); expect(a.locator("#sendb")).to_be_visible(timeout=T)
    assert a.locator("[data-tip], .tipb").count() == 0 and "💸 Tip" not in a.inner_text("#app")
    a.screenshot(path=f"{SHOTS}/tips2-1-no-tip-button.png")
    for body in ({"recipient": bid, "amount_cents": 500}, {"recipient": bid, "purpose": "thanks", "amount_cents": 500}, {"recipient": bid, "purpose": "listen", "amount_cents": 500}):
        r = fn(a, "tips2-checkout", body); assert "Tips go with a clip" in r.get("error", ""), (body, r)
    r = fn(a, "tips2-checkout", {"recipient": bid, "purpose": "listen", "kind": "bridge", "ref": "00000000-0000-4000-8000-000000000000", "amount_cents": 500}); assert "not found" in r.get("error", "").lower(), r
    assert q1("select count(*) from tips2 where recipient=%s", (bid,))[0] == 0
    step("No Tip button on People/profile pages; tips2-checkout rejects tips not attached to a valid clip (thank-you, no clip, bogus clip)")
    r = fn(a, "tips-checkout", {"recipient": bid, "amount_cents": 500}); assert "hasn't set up tips yet" in r.get("error", ""), r
    step("Live v1 tips-checkout still refuses (unchanged)")
    # Settings card hidden for people with no tips
    b.goto(BASE + "#profile"); b.click("[data-pt=Settings]"); b.wait_for_timeout(2500); assert b.locator("#tipcard").count() == 0
    step("No 'Get paid' card in Settings before earning a tip")
    # A and B friends, group pod
    ev(a, "async u=>{const{error}=await sb.rpc('send_friend_request',{p_user:u});if(error)throw error}", bid)
    ev(b, "async u=>{const{error}=await sb.rpc('respond_friend_request',{p_user:u,p_accept:true});if(error)throw error}", aid)
    pod = ev(a, "async([n,u])=>{const{data,error}=await sb.rpc('create_group_pod',{p_name:n,p_members:[u]});if(error)throw error;return data}", [f"Smoke tip pod {tag}", bid])
    pod = pod if isinstance(pod, str) else (pod.get("id") if isinstance(pod, dict) else pod[0])
    a.goto(BASE + f"#pod/{pod}"); a.click("#gsharebtn"); a.fill("#gsurl", "https://example.org/listen-tip"); a.fill("#gstitle", f"Smoke listen clip {tag}")
    a.check("#gstip"); a.click("#gsgo"); sh = a.locator("#tipsheet"); expect(sh).to_be_visible(timeout=T)
    expect(sh.locator("#tiph")).to_have_text("Add a tip for listening"); expect(sh).to_contain_text(f"{Bn} gets it after they answer & rate this clip")
    expect(sh.locator(".tipbrk .tot")).to_contain_text("$5.46"); a.screenshot(path=f"{SHOTS}/tips2-2-tip-to-listen.png")
    step("Sharing a clip with '💸 Add a tip for listening' opens the listening-tip sheet ($5 → $5.46)")
    a.click("#tipgo"); a.wait_for_url(MOCK + "/mock/checkout/**", timeout=T); cs = a.url.rsplit("/", 1)[1]; f = mock("/mock/state")["sessions"][cs]["form"]
    assert "payment_intent_data[transfer_data][destination]" not in f and "payment_intent_data[application_fee_amount]" not in f, f
    assert f["line_items[0][price_data][unit_amount]"] == "500" and f["line_items[1][price_data][unit_amount]"] == "46" and "for listening" in f["line_items[0][price_data][product_data][name]"], f
    assert f.get("adaptive_pricing[enabled]") == "false", f  # USD-only app (TIPS_USD_ONLY_APPS)
    t = q1("select status, mode, purpose, total_cents, recipient_cents, recipient from tips2 where checkout_session_id=%s", (cs,)); assert t[:5] == ("pending", "platform", "listen", 546, 450) and str(t[5]) == bid, t
    a.click("#pay"); a.wait_for_url("**#tipped/**", timeout=T); expect(a.locator("#app")).to_contain_text(f"Your $5.00 tip is waiting for {Bn}")
    assert q1("select status from tips2 where checkout_session_id=%s", (cs,))[0] == "held"
    step("Platform Checkout (no destination/application fee), $5.00 + $0.46; paid → tip 'held', amount due $4.50")
    b.goto(BASE + "#notifications"); expect(b.locator(".nlist li").first).to_contain_text(f"{A} added a $5 tip for listening to", timeout=T)
    b.goto(BASE + f"#pod/{pod}"); w = b.locator(".tipwait").first; expect(w).to_contain_text("$5 tip waiting: listen and answer to earn it", timeout=T)
    b.evaluate("document.querySelector('.tipwait').scrollIntoView({block:'center'})"); b.wait_for_timeout(300); b.screenshot(path=f"{SHOTS}/tips2-3-waiting.png")
    a.goto(BASE + f"#pod/{pod}"); expect(a.locator(".tipsent").first).to_contain_text(f"Your $5 tip for {Bn} is waiting", timeout=T)
    step("Listener: notification + '$5 tip waiting: listen and answer to earn it' on the clip; tipper sees it's waiting")
    clip = str(q1("select pod_ref from tips2 where checkout_session_id=%s", (cs,))[0])
    r = fn(a, "tips2-checkout", {"recipient": aid, "purpose": "listen", "kind": "group_clip", "ref": clip, "amount_cents": 500}); assert "yourself" in r.get("error", ""), r
    # B answers → earned
    b.fill(f"#ga-{clip}", "It was about listening carefully."); b.locator(f"fieldset.rate[data-rk='{clip}'] [role=radio]").nth(8).click()
    b.click(f"[data-gans='{clip}']"); b.wait_for_timeout(2500)
    assert q1("select status from tips2 where checkout_session_id=%s", (cs,))[0] == "earned"
    b.goto(BASE + f"#pod/{pod}"); expect(b.locator(f"[data-ltip='{clip}']")).to_be_visible(timeout=T)  # answered → may tip others to listen
    r = fn(a, "tips2-checkout", {"recipient": bid, "purpose": "listen", "kind": "group_clip", "ref": clip, "amount_cents": 500}); assert "already answered" in r.get("error", ""), r
    b.goto(BASE + "#notifications"); expect(b.locator(".nlist li").first).to_contain_text("You earned $5 for listening to", timeout=T)
    b.goto(BASE + "#profile"); b.click("[data-pt=Settings]"); e = b.locator("#tipearned"); expect(e).to_contain_text("You've earned $4.50 in tips", timeout=T)
    b.evaluate("document.querySelector('#tipcard').scrollIntoView({block:'center'})"); b.wait_for_timeout(300); b.screenshot(path=f"{SHOTS}/tips2-4-earned.png")
    step("Answering earns it: 'You earned $5 for listening…' + Settings 'You've earned $4.50 in tips. Get paid'; no more listen tips once answered")
    # one-friend invite with a tip: A sends B a clip from B's profile and adds a tip in the same step
    a.goto(BASE + f"#u/{bid}"); a.click("#sendb"); a.fill("#sdurl", "https://example.org/invite-tip"); a.fill("#sdtitle", f"Smoke invite tip {tag}")
    a.check("#sdtip"); a.click("#sdgo"); sh = a.locator("#tipsheet"); expect(sh.locator("#tiph")).to_have_text("Add a tip for listening", timeout=T)
    expect(sh.locator(".tipbrk .tot")).to_contain_text("$5.46"); a.click("#tipgo"); a.wait_for_url("**/mock/checkout/**", timeout=T); ics = a.url.rsplit("/", 1)[1]
    mock("/mock/pay/" + ics, {"x": "1"}); a.goto(BASE + "#bridges"); a.wait_for_function("typeof sb!=='undefined'"); it = q1("select status, purpose, pod_kind, pod_ref, recipient from tips2 where checkout_session_id=%s", (ics,))
    assert it[:3] == ("held", "listen", "bridge") and str(it[4]) == bid, it
    assert q1("select direct_status from bridges where id=%s", (it[3],))[0] == "pending"
    b.goto(BASE + "#bridges"); expect(b.locator(f"#inc-{it[3]} .tipwait")).to_contain_text("$5 tip waiting: listen and answer to earn it", timeout=T)
    step("Invite with a tip: 'Send a clip' to a friend + '💸 Add a tip for listening' → held on the pending invite; the friend sees '$5 tip waiting: listen and answer to earn it' on it")
    b.goto(BASE + "#profile"); b.click("[data-pt=Settings]"); expect(b.locator("#tipcard #tipon")).to_be_visible(timeout=T)
    b.click("#tipcard #tipon"); b.wait_for_url("**#tipsetup/return", timeout=T); expect(b.locator("#tipcard")).to_contain_text("Payouts are on", timeout=T)
    expect(b.locator("#tipcard")).to_contain_text("$4.50 sent", timeout=T)
    tid = str(q1("select id from tips2 where checkout_session_id=%s", (cs,))[0]); mine = lambda: [x for x in mock("/mock/state")["transfers"] if x["transfer_group"] == f"tip_{tid}"]
    st = mock("/mock/state"); tr = mine(); assert len(tr) == 1 and tr[0]["amount"] == 450, tr
    pi = q1("select payment_intent_id, charge_id, transfer_id, status from tips2 where checkout_session_id=%s", (cs,))
    assert pi[3] == "paid_out" and tr[0]["source_transaction"] == st["pis"][pi[0]]["latest_charge"] == pi[1] and tr[0]["id"] == pi[2], (pi, tr)
    acct = q1("select stripe_account_id from tip_accounts2 where user_id=%s", (bid,))[0]; assert tr[0]["destination"] == acct
    assert q1("select count(*) from tip_accounts where user_id=%s", (bid,))[0] == 0
    step("Get paid → Stripe onboarding (v2) → return: Transfer $4.50 to the new account with source_transaction = the charge; 'paid out'")
    ac = mock("/mock/state")["accts"][acct]; assert ac["mcc"] == "7299" and ac["identity"]["individual"]["email"] and ac["defaults"]["profile"]["business_url"].startswith(BASE), ac
    step("Prefill (TIPS_PREFILL_APPS): new account created with MCC 7299, email and website already set")
    mock("/mock/reject", {"account": acct}); mock("/mock/disable", {"account": acct}); fn(b, "tips2-connect", {"action": "status"})
    n0 = len(mock("/mock/state")["updates"]); r = fn(b, "tips2-connect", {"action": "onboard"}); assert r.get("url"), r
    ups = [x for x in mock("/mock/state")["updates"][n0:] if x["account"] == acct]; assert len(ups) >= 2, ups
    mock("/mock/enable", {"account": acct}); fn(b, "tips2-connect", {"action": "status"})
    step("Prefill is best effort: Stripe refuses every prefill write (combined + per field) and onboard still returns a link")
    fn(b, "tips2-connect", {"action": "status"}); code, out = sweep(); assert code == 200, out
    assert len(mine()) == 1; assert sweep("nope")[0] == 403
    step("Idempotent: repeat status + cron sweep make no second transfer; sweep needs the cron secret")
    # onboarded recipient keeps destination charges
    r = fnL(a, "tips2-checkout", {"recipient": bid, "amount_cents": 500}); assert r.get("mode") == "destination", r
    f = mock("/mock/state")["sessions"][r["url"].rsplit("/", 1)[1]]["form"]; assert f["payment_intent_data[application_fee_amount]"] == "96" and f["payment_intent_data[transfer_data][destination]"] == acct, f
    mock("/mock/pay/" + r["url"].rsplit("/", 1)[1], {"x": "1"}); assert q1("select status from tips2 where id=%s", (r["tip_id"],))[0] == "paid_out"
    step("Onboarded recipient: thank-you tip is a destination charge (application fee $0.96) → paid out")
    # not-onboarded thank-you tip: earned on payment
    r = fnL(b, "tips2-checkout", {"recipient": cid, "amount_cents": 500}); assert r.get("mode") == "platform", r
    mock("/mock/pay/" + r["url"].rsplit("/", 1)[1], {"x": "1"}); assert q1("select status from tips2 where id=%s", (r["tip_id"],))[0] == "earned"
    c.goto(BASE + "#notifications"); expect(c.locator(".nlist li").first).to_contain_text(f"{Bn} tipped you $5. Set up payouts to collect it", timeout=T)
    step("Not-onboarded recipient: thank-you tip on the platform, earned on payment, 'X tipped you $5. Set up payouts to collect it'")
    # refunds: earned unclaimed 90 days; held listen tip after 30 days
    clip2 = ev(a, "async([p,t])=>await API.gshare(p,{url:'https://example.org/listen-2',title:t,type:'Podcast'},'')", [pod, f"Smoke listen 2 {tag}"])
    r2 = fn(a, "tips2-checkout", {"recipient": bid, "purpose": "listen", "kind": "group_clip", "ref": clip2, "amount_cents": 200}); mock("/mock/pay/" + r2["url"].rsplit("/", 1)[1], {"x": "1"})
    assert q1("select status from tips2 where id=%s", (r2["tip_id"],))[0] == "held"
    code, out = sweep(); assert code == 200 and [q1("select status from tips2 where id=%s", (x,))[0] for x in (r["tip_id"], r2["tip_id"])] == ["earned", "held"], out
    nref = len(mock("/mock/state")["refunds"])
    db.execute("update tips2 set earned_at = now() - interval '91 days' where id=%s", (r["tip_id"],))
    db.execute("update tips2 set paid_at = now() - interval '31 days' where id=%s", (r2["tip_id"],))
    code, out = sweep(); assert code == 200 and out["refunds"] >= 2, out
    assert [q1("select status from tips2 where id=%s", (x,))[0] for x in (r["tip_id"], r2["tip_id"])] == ["refunded", "refunded"]
    assert len(mock("/mock/state")["refunds"]) == nref + 2; code, out = sweep(); assert len(mock("/mock/state")["refunds"]) == nref + 2
    step("Sweep refunds earned tips unclaimed for 90 days and listening tips not earned within 30 days (once)")
    # blocks
    ev(b, "async u=>{const{error}=await sb.rpc('block_user',{p_user:u});if(error)throw error}", cid)
    r = fnL(c, "tips2-checkout", {"recipient": bid, "amount_cents": 500}); assert "not found" in r.get("error", "").lower(), r
    assert c.evaluate("async u=>(await sb.rpc('tips2_can_tip',{p_user:u})).data", bid) is False
    ev(b, "async u=>{await sb.rpc('unblock_user',{p_user:u})}", cid); step("Blocks respected")
    evl = json.dumps({"id": "evt_l", "type": "checkout.session.completed", "livemode": True, "data": {"object": {"id": "cs_x", "payment_status": "paid"}}})
    import subprocess; hdr = subprocess.run(["node", "-e", "const c=require('crypto'),t=Math.floor(Date.now()/1000),b=process.argv[1];console.log('t='+t+',v1='+c.createHmac('sha256','whsec_local_mock').update(t+'.'+b).digest('hex'))", evl], capture_output=True, text=True).stdout.strip()
    try: urllib.request.urlopen(urllib.request.Request(API + "/functions/v1/tips2-webhook", data=evl.encode(), method="POST", headers={"stripe-signature": hdr})); raise AssertionError("live event accepted with sandbox secret")
    except urllib.error.HTTPError as e: assert e.code == 400, e.code
    step("Webhook: a livemode event signed with the sandbox secret is rejected (mode must match the verifying secret)")
    assert not errors, errors
print(f"\n{n} tips2 checks passed")
