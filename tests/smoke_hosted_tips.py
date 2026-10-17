"""Hosted smoke for tips (preview). Creates NO Stripe objects and charges nothing: two Smoke* users (anonymous sign-in +
operator-confirmed @example.invalid emails via tests/hosted_users.py), then checks the not-set-up note, the Settings
'Get paid for tips' card, server-side refusals and the Tips terms. Clean up Smoke* users afterwards."""
import os, time
from playwright.sync_api import sync_playwright, expect
import hosted_users
BASE = os.environ["BASE"]; SHOTS = os.environ.get("SHOTS_DIR", "/tmp/shots-hosted-tips"); os.makedirs(SHOTS, exist_ok=True)
T = 30000; n = 0; tag = str(int(time.time()) % 100000)
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    def phone(who):
        c = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}})
        pg = c.new_page(); pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); pg.on("dialog", lambda d: d.accept()); return pg
    a, b = phone("A"), phone("B")
    aid = hosted_users.make(a, BASE, f"SmokeTipA{tag}"); bid = hosted_users.make(b, BASE, f"SmokeTipB{tag}")
    hosted_users.confirm(BASE, [(a, aid), (b, bid)])
    b.goto(BASE + f"#u/{aid}"); expect(b.locator(f"[data-tipno='{aid}']")).to_have_text(f"SmokeTipA{tag} hasn't set up tips yet", timeout=T)
    assert b.locator("[data-tip]").count() == 0; b.screenshot(path=f"{SHOTS}/tips-h-notsetup.png"); step("Profile of someone not set up: 'X hasn't set up tips yet', no Tip button")
    r = b.evaluate("async u=>{try{return await tipFn('tips-checkout',{recipient:u,amount_cents:500})}catch(e){return{error:e.message}}}", aid)
    assert r.get("error") in (f"SmokeTipA{tag} hasn't set up tips yet", "Tips aren't available yet"), r; step(f"Server refuses a tip to them: {r['error']!r}")
    r = b.evaluate("async u=>{try{return await tipFn('tips-checkout',{recipient:u,amount_cents:500})}catch(e){return{error:e.message}}}", bid)
    assert r.get("error") in ("You can't tip yourself", "Tips aren't available yet"), r; step(f"No tipping yourself: {r['error']!r}")
    a.goto(BASE + "#profile"); a.click("[data-pt=Settings]"); card = a.locator("#tipcard"); expect(card).to_contain_text("Get paid for tips", timeout=T)
    expect(card.locator("p")).not_to_have_text("Loading…", timeout=T); st = card.inner_text(); a.screenshot(path=f"{SHOTS}/tips-h-settings.png")
    step("Settings shows the 'Get paid for tips' card: " + ("button ready" if a.locator("#tipon").count() else "'Tips aren't available right now' (Stripe not configured)"))
    assert b.evaluate("async u=>(await sb.rpc('tips_enabled_for',{p_user:u})).data", aid) is False
    assert b.evaluate("async()=>(await sb.from('tip_accounts').select('user_id')).data.length") == 0 and b.evaluate("async()=>(await sb.from('tips').select('id')).data.length") == 0
    step("RLS: no one else's tip accounts or tips visible")
    b.goto(BASE + "terms.html#tips"); expect(b.locator("#tips")).to_have_text("Tips"); expect(b.locator("body")).to_contain_text("Pod Club keeps 10%"); step("Terms: Tips section")
    assert not errors, errors
print(f"\nhosted tips smoke: {n} checks passed")
print("SMOKE_IDS", aid, bid)
