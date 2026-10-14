"""Hosted smoke for Remind v2 + email-only sign-up. Sends NO email: Remind runs in DRY RUN (window.REMIND_DRY), and no
sign-up/keep form is ever submitted. Users are Smoke* legacy anon accounts; two get @example.invalid emails confirmed by
the operator via SQL (handoff files) so the email path can be dry-run. Clean up Smoke* users afterwards."""
import json, os, re, time
from playwright.sync_api import sync_playwright, expect
BASE = os.environ["BASE"]; HO = os.environ.get("HANDOFF", "/tmp/remind2-handoff"); SHOTS = os.environ.get("SHOTS_DIR", "/tmp/shots-hosted"); os.makedirs(SHOTS, exist_ok=True)
T = 30000; n = 0; tag = str(int(time.time()) % 100000)
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    def phone(who):
        c = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}}); c.add_init_script("window.REMIND_DRY=true")
        pg = c.new_page(); pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); pg.on("dialog", lambda d: d.accept()); return pg
    shot = lambda pg, nm: (pg.wait_for_timeout(400), pg.screenshot(path=f"{SHOTS}/{nm}.png"))
    a, b, g = phone("A"), phone("B"), phone("G")
    a.goto(BASE); expect(a.locator("#sbtn")).to_be_visible(timeout=T); a.click("#sbtn"); expect(a.locator("#em")).to_be_visible(); expect(a.locator("#nok")).to_have_text("Email me a code")
    expect(a.locator("#su")).not_to_contain_text("No email or password needed"); shot(a, "h-welcome"); step("Preview: Sign Up asks for name + email (not submitted)")
    mkanon = "async n=>{const{data,error}=await sb.auth.signInAnonymously();if(error)throw error;const r=await sb.from('profiles').insert({id:data.user.id,display_name:n,topics:['Science']});if(r.error)throw r.error;return data.user.id}"
    ids = {}
    for pg, k in ((a, "a"), (b, "b"), (g, "g")): pg.goto(BASE); ids[k] = pg.evaluate(mkanon, f"Smoke{k.upper()}x{tag}")
    g.reload(); expect(g.get_by_text("Add your email to keep your account")).to_be_visible(timeout=T); assert g.get_by_text("Skip").count() == 0; shot(g, "h-keep")
    g.goto(BASE + "#bridges"); expect(g.get_by_text("Add your email to keep your account")).to_be_visible(timeout=T); step("Existing guest: required 'Add your email to keep your account' (no skip)")
    mk = "async t=>{const{data,error}=await sb.rpc('create_bridge',{p_display_name:'SmokeAx"+tag+"',p_clip_title:t,p_clip_url:'https://example.org/'+encodeURIComponent(t),p_clip_type:'Podcast',p_clip_cat:'',p_clip_creator:'',p_friend_label:'',p_reward:''});if(error)throw error;return data[0]||data}"
    b1 = a.evaluate(mk, f"Smoke r2 guest {tag}"); g.evaluate("async([t,n])=>{const{error}=await sb.rpc('join_bridge',{p_token:t,p_display_name:n});if(error)throw error}", [b1["invite_token"], f"SmokeGx{tag}"])
    b0 = a.evaluate(mk, f"Smoke r2 unused {tag}")
    dp = a.evaluate("async u=>{const{data,error}=await sb.rpc('send_direct_bridge',{p_to:u,p_clip_title:'Smoke r2 direct',p_clip_url:'https://example.org/r2d',p_clip_type:'Podcast'});if(error)throw error;return data}", ids["b"])
    open(HO + ".ids", "w").write(json.dumps({"a": ids["a"], "b": ids["b"], "tag": tag}))
    for _ in range(600):
        if os.path.exists(HO + ".ok"): break
        time.sleep(1)
    else: raise AssertionError("operator never confirmed")
    for pg in (a, b): pg.evaluate("async()=>{const{error}=await sb.auth.refreshSession();if(error)throw error}")
    a.goto(BASE + f"#bridge/{b1['id']}/0"); a.reload(); rb = a.locator(f".remrow [data-rmd='{ids['g']}']"); expect(rb).to_be_visible(timeout=T); rb.click()
    expect(a.locator(".toast")).to_contain_text("Dry run ✓ in-app only", timeout=T); shot(a, "h-guest"); step("Joined guest partner: Remind shows; dry run says in-app only")
    a.goto(BASE + f"#bridge/{dp}/0"); pb = a.locator(f"#rempend [data-rmd='{ids['b']}']"); expect(pb).to_be_visible(timeout=T); pb.click()
    expect(a.locator(".toast")).to_contain_text("Dry run ✓ would email", timeout=T); shot(a, "h-pending"); step("Pending direct send: Remind shows; dry run would email a masked address")
    a.goto(BASE + f"#bridge/{b0['id']}/0"); expect(a.locator("#reinv #rsi")).to_be_visible(timeout=T); assert a.locator("[data-rmd]").count() == 0; step("Unused invite link: 'Resend invite' instead of Remind")
    v = phone("V"); v.goto(BASE + "#b/" + b0["invite_token"]); expect(v.locator("#jname")).to_be_visible(timeout=T); expect(v.locator("#em")).to_be_visible(); shot(v, "h-invite"); step("Invite landing asks for name + email (not submitted)")
    assert a.evaluate("async()=>{const{count}=await sb.from('pod_reminders').select('id',{count:'exact',head:true});return count}") == 0; step("Dry runs stored no reminders")
    st = a.evaluate("async()=>(await fetch(CFG.SUPABASE_URL+'/functions/v1/remind',{method:'POST',headers:{apikey:CFG.SUPABASE_ANON_KEY,'Content-Type':'application/json'},body:'{}'})).status")
    assert st == 401, st; step("Function rejects unauthenticated calls")
    assert not errors, errors; step("No JS errors"); br.close()
print(f"Hosted remind v2 smoke: {n} checks passed")
