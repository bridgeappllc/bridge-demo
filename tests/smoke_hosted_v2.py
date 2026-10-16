"""Hosted-safe smoke test for v2 (2 Smoke email accounts made out-of-band, sends NO email):
add to library, start a pod from an item, friend
joins and views/copies from your library, sign-up + invite screens ask for email (not submitted),
and sign-in with an unknown address is refused by the API (no account, no email)."""
import json, os, re, time
from hosted_users import make, confirm
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8081/"); P = os.environ.get("P", "SmokePaul"); S = os.environ.get("S", "SmokeSam")
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 25000; n = 0
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
LEGACY = {"topics": [], "clips": [{"id": "k999", "title": "Smoke old saved podcast", "creator": "Added by you", "type": "Podcast", "cat": "Culture", "url": "https://example.org/smoke-old-pod", "note": "saved before accounts existed", "rating": 5, "votes": 0, "lib": 1}]}
with sync_playwright() as p:
    br = p.chromium.launch(); iphone = p.devices["iPhone 13"]; errors = []
    def page(ctx, who):
        pg = ctx.new_page(); pg.on("dialog", lambda d: d.accept()); pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); return pg
    def shot(pg, name):
        try: pg.screenshot(path=f"{SHOTS}/{name}.png", timeout=15000)
        except Exception: print("    (screenshot skipped)", name)
    # unknown email -> refused, before any sign-up (no account is created, no email sent)
    anon = page(br.new_context(**iphone), "signin")
    anon.goto(BASE); anon.click("#lbtn"); expect(anon.get_by_text("Welcome back")).to_be_visible(timeout=T); shot(anon, "signin")
    anon.fill("#em", f"smoke-nobody-{int(time.time())}@example.com"); anon.click("#esend")
    expect(anon.locator("#emsg")).to_contain_text("No Pod Club account uses that email", timeout=T); step("Sign-in API refuses an unknown email (no account created, no email sent)")
    paul = page(br.new_context(**iphone), "paul"); sam = page(br.new_context(**iphone), "sam")
    pid = make(paul, BASE, P); sid = make(sam, BASE, S); confirm(BASE, [(paul, pid), (sam, sid)]); step("Two Smoke email accounts (no sign-up form, no email sent)")
    paul.goto(BASE + "#profile"); expect(paul.locator("h1")).to_contain_text(P, timeout=T)
    expect(paul.locator(".tabs [data-pt=Add]")).to_be_visible(timeout=T); paul.click(".tabs [data-pt=Add]"); paul.fill("#aurl", "https://www.youtube.com/watch?v=smoke-lib"); paul.fill("#atitle", "Smoke test video"); paul.select_option("#acat", "Science")
    paul.fill("#anote", "Changed how I think about energy."); paul.click("#asave"); expect(paul.get_by_text("Changed how I think about energy.")).to_be_visible(timeout=T)
    paul.goto(BASE + "#profile"); expect(paul.locator(".stat")).to_contain_text("1Library", timeout=T); paul.wait_for_timeout(600); shot(paul, "library"); step("Add to Library saves online")
    paul.locator(".card", has_text="Smoke test video").locator(".lmeta").click(); paul.click("text=Check this out")
    expect(paul.locator("#mclip")).to_have_value(re.compile(r"[0-9a-f-]{36}"), timeout=T); paul.fill("#mfriend", S); paul.click("#mgo")
    expect(paul.locator("#itxt")).to_be_visible(timeout=T); link = re.search(r"(https?://\S+#b/[0-9a-f]{32})", paul.locator("#itxt").input_value()).group(1)
    expect(paul.locator("#savenote")).to_have_count(0); step("Bridge started from a library item")
    sam.goto(link); expect(sam.locator("#jgo")).to_be_visible(timeout=T); assert sam.locator("#em").count() == 0; sam.click("#jgo"); expect(sam.get_by_text("Answer & rate")).to_be_visible(timeout=T)
    sam.click(f"text={P}'s library"); expect(sam.locator(".card", has_text="Smoke test video")).to_be_visible(timeout=T)
    sam.wait_for_timeout(600); shot(sam, "friend-library")
    sam.locator(".card", has_text="Smoke test video").locator(".lmeta").click(); expect(sam.get_by_text(f"{P}'s note:")).to_be_visible(timeout=T); sam.click("#addlib")
    expect(sam.get_by_text("✓ In your library")).to_be_visible(timeout=T); step("Friend views your library (with notes) and adds an item to theirs")
    v = page(br.new_context(**iphone), "visitor"); v.goto(BASE); v.click("#sbtn"); expect(v.locator("#em")).to_be_visible(); expect(v.locator("#nok")).to_have_text("Email me a code")
    tok2 = paul.evaluate("async()=>{const{data,error}=await sb.rpc('create_bridge',{p_display_name:PROFILE.display_name,p_clip_title:'Smoke invite page',p_clip_url:'https://example.org/sip',p_clip_type:'Podcast',p_clip_cat:'',p_clip_creator:'',p_friend_label:'',p_reward:''});if(error)throw error;return (data[0]||data).invite_token}")
    v.goto(BASE + "#b/" + tok2); expect(v.locator("#jname")).to_be_visible(timeout=T); expect(v.locator("#em")).to_be_visible(); shot(v, "invite-signup")
    step("Sign Up and invite landing ask for name + email (not submitted, no email sent)")
    assert not errors, errors; step("No uncaught JS errors"); br.close()
print(f"\nHosted v2 smoke: {n} checks passed")
