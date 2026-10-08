"""Hosted-safe smoke test for v2 (2 anonymous sign-ups, sends NO email):
old local library migrates, add to library, start a bridge from an item, friend
joins and views/copies from your library, save-account + sign-in screens render,
and sign-in with an unknown address is refused by the API (no account, no email)."""
import json, os, re, time
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
    expect(anon.locator("#emsg")).to_contain_text("No Bridge account uses that email", timeout=T); step("Sign-in API refuses an unknown email (no account created, no email sent)")
    pc = br.new_context(**iphone)
    pc.add_init_script("if(!sessionStorage.getItem('seeded')){localStorage.setItem('bridge_real_v1', %s);sessionStorage.setItem('seeded','1')}" % json.dumps(json.dumps(LEGACY)))
    paul = page(pc, "paul")
    paul.goto(BASE); paul.click("#sbtn"); paul.fill("#nm", P); paul.click("#nok"); expect(paul.get_by_text("Pick your topics")).to_be_visible(timeout=T)
    [paul.click(f".topic[data-t={t}]") for t in ("Politics", "Science", "Culture")]; paul.click("#tgo")
    paul.goto(BASE + "#profile"); expect(paul.locator(".card", has_text="Smoke old saved podcast")).to_be_visible(timeout=T); step("Old device-local library item migrated online")
    paul.click("[data-pt=Add]"); paul.fill("#aurl", "https://www.youtube.com/watch?v=smoke-lib"); paul.fill("#atitle", "Smoke test video"); paul.select_option("#acat", "Science")
    paul.fill("#anote", "Changed how I think about energy."); paul.click("#asave"); expect(paul.get_by_text("Changed how I think about energy.")).to_be_visible(timeout=T)
    paul.goto(BASE + "#profile"); expect(paul.locator(".stat")).to_contain_text("2Library", timeout=T); paul.wait_for_timeout(600); shot(paul, "library"); step("Add to Library saves online")
    paul.locator(".card", has_text="Smoke test video").click(); paul.click("text=🌉 Meet me on the Bridge with this")
    expect(paul.locator("#mclip")).to_have_value(re.compile(r"[0-9a-f-]{36}"), timeout=T); paul.fill("#mfriend", S); paul.click("#mgo")
    expect(paul.locator("#itxt")).to_be_visible(timeout=T); link = re.search(r"(https?://\S+#b/[0-9a-f]{32})", paul.locator("#itxt").input_value()).group(1)
    expect(paul.locator("#savenote")).to_be_visible(); step("Bridge started from a library item; 'Save your account' prompt shown")
    sam = page(br.new_context(**iphone), "sam"); sam.goto(link); sam.fill("#jname", S); sam.click("#jgo"); expect(sam.get_by_text("Answer three questions")).to_be_visible(timeout=T)
    sam.click(f"text={P}'s library"); expect(sam.locator(".card", has_text="Smoke test video")).to_be_visible(timeout=T)
    expect(sam.locator(".card", has_text="Smoke old saved podcast")).to_be_visible(); sam.wait_for_timeout(600); shot(sam, "friend-library")
    sam.locator(".card", has_text="Smoke test video").click(); expect(sam.get_by_text(f"{P}'s note:")).to_be_visible(timeout=T); sam.click("#addlib")
    expect(sam.get_by_text("✓ In your library")).to_be_visible(timeout=T); step("Friend views your library (with notes) and adds an item to theirs")
    paul.goto(BASE + "#account"); expect(paul.get_by_text("Save your account").first).to_be_visible(timeout=T); paul.wait_for_timeout(400); shot(paul, "save-account")
    step("Save-your-account screen renders (no email sent on hosted)")
    assert not errors, errors; step("No uncaught JS errors"); br.close()
print(f"\nHosted v2 smoke: {n} checks passed")
