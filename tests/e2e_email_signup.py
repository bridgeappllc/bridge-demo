"""E2E (LOCAL only): no more guest sign-in. New users sign up with name + email + emailed code (welcome and invite
landing); an existing email just signs in; legacy guest accounts must add an email (same user id kept) before anything else."""
import os, time
from authflow import signup_email, join_email, code_for, mails, email_for
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); assert "127.0.0.1" in BASE, "local only: sends code emails"
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 30000; n = 0; tag = str(int(time.time()) % 100000)
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    def phone(who):
        pg = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}}).new_page()
        pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); pg.on("dialog", lambda d: d.accept()); return pg
    shot = lambda pg, nm: (pg.wait_for_timeout(300), pg.screenshot(path=f"{SHOTS}/su-{nm}.png"))
    # 1. welcome sign-up
    a = phone("A"); a.goto(BASE); a.click("#sbtn"); expect(a.locator("#nm")).to_be_visible(); expect(a.locator("#em")).to_be_visible()
    expect(a.locator("#su")).not_to_contain_text("No email or password needed"); expect(a.locator("#nok")).to_have_text("Email me a code"); shot(a, "1-welcome")
    a.fill("#nm", f"SmokeAva{tag}"); a.fill("#em", "not-an-email"); a.click("#nok"); expect(a.locator("#emsg")).to_contain_text("valid email"); assert a.evaluate("ME") is None
    step("Sign Up asks for name + email (no guest option); bad email rejected before any account exists")
    AE = signup_email(a, f"SmokeAva{tag}"); expect(a.get_by_text("Pick your topics")).to_be_visible(timeout=T)
    assert a.evaluate("USER.is_anonymous") is False and a.evaluate("USER.email") == AE and a.evaluate("PROFILE.display_name") == f"SmokeAva{tag}"
    a.click("text=Skip"); expect(a.get_by_text("Your Pods")).to_be_visible(timeout=T); aid = a.evaluate("ME")
    step("Code from the email -> signed in with a real (non-guest) account, profile created with the name")
    # 2. same email again on another phone = sign in to that account
    a2 = phone("A2"); a2.goto(BASE); a2.click("#sbtn"); signup_email(a2, f"SmokeAva{tag}", AE); expect(a2.get_by_text("Your Pods")).to_be_visible(timeout=T)
    assert a2.evaluate("ME") == aid; step("Signing up with an email that already has an account just signs in to it (same user)")
    # 3. invite landing
    tok = a.evaluate("async()=>{const{data,error}=await sb.rpc('create_bridge',{p_display_name:PROFILE.display_name,p_clip_title:'Smoke signup clip',p_clip_url:'https://example.org/ssc',p_clip_type:'Podcast',p_clip_cat:'',p_clip_creator:'',p_friend_label:'',p_reward:''});if(error)throw error;return (data[0]||data).invite_token}")
    b = phone("B"); b.goto(BASE + "#b/" + tok); expect(b.locator("#jname")).to_be_visible(timeout=T); expect(b.locator("#em")).to_be_visible(); shot(b, "2-invite")
    b.fill("#jname", f"SmokeBo{tag}"); b.click("#jgo"); expect(b.locator("#emsg")).to_contain_text("valid email"); assert b.evaluate("ME") is None
    join_email(b, f"SmokeBo{tag}"); expect(b.get_by_text("Answer & rate")).to_be_visible(timeout=T); assert b.evaluate("USER.is_anonymous") is False
    step("Invite landing: name + email + code, then joined the pod (no guest join)")
    # 4. legacy guest -> required 'Add your email to keep your account'
    g = phone("G"); g.goto(BASE)
    gid = g.evaluate("async n=>{const{data,error}=await sb.auth.signInAnonymously();if(error)throw error;const r=await sb.from('profiles').insert({id:data.user.id,display_name:n,topics:[]});if(r.error)throw r.error;return data.user.id}", f"SmokeGil{tag}")
    g.goto(BASE + "#people"); g.reload(); expect(g.get_by_text("Add your email to keep your account")).to_be_visible(timeout=T)
    assert g.locator("#nav button").count() == 0 or not g.locator("#nav").is_visible(); assert g.get_by_text("Skip").count() == 0 and g.get_by_text("Not now").count() == 0; shot(g, "3-keep")
    for h in ("#bridges", "#profile", "#new"): g.goto(BASE + h); expect(g.get_by_text("Add your email to keep your account")).to_be_visible(timeout=T)
    step("Existing guest: required 'Add your email to keep your account' screen on every route, no nav, no skip")
    GE = email_for("smokegil"); before = len(mails(GE)); g.fill("#em", GE); g.click("#esend"); expect(g.locator("#code")).to_be_visible(timeout=T); g.fill("#code", code_for(GE, before)); g.click("#cok")
    expect(g.get_by_text("Add your email to keep your account")).to_have_count(0, timeout=T); expect(g.locator("#nav")).to_be_visible()
    assert g.evaluate("ME") == gid and g.evaluate("USER.is_anonymous") is False and g.evaluate("PROFILE.display_name") == f"SmokeGil{tag}"
    assert "#new" in g.url, g.url; step("Email linked to the same user (id + profile kept), then back where they were headed")
    w = g.evaluate("document.documentElement.scrollWidth"); assert w <= 375, w
    assert not errors, errors; step("No overflow, no JS errors"); br.close()
print(f"E2E email sign-up: {n} checks passed")
