"""E2E for v2 features: online library (+ migration of old device-local items),
bridge partners viewing your library, starting a bridge from a library item,
'Save your account' (guest -> email, same user id) and email-code sign-in on a
second browser with library/bridges syncing. Needs a mail catcher (Mailpit) whose
API is at MAILPIT (default http://127.0.0.1:8025) — local stack only."""
import json, os, re, time, urllib.request
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/")
MAILPIT = os.environ.get("MAILPIT", "http://127.0.0.1:8025")
HERE = os.path.dirname(os.path.abspath(__file__)); SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(HERE, "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 20000; results = []
def step(n): results.append(n); print("  ✓", n, flush=True)
def mails(addr): return json.load(urllib.request.urlopen(f"{MAILPIT}/api/v1/search?query=to:{urllib.parse.quote(addr)}"))["messages"]
def new_code(addr, before):
    for _ in range(40):
        m = mails(addr)
        if len(m) > before: return re.search(r"(\d{6,10})", m[0]["Subject"]).group(1), m[0]["Subject"]
        time.sleep(0.5)
    raise AssertionError("no email for " + addr)
import urllib.parse
ts = int(time.time()); PAUL_EMAIL = f"smoke-paul-{ts}@test.local"
LEGACY = {"topics": ["Culture"], "clips": [
    {"id": "k1", "ex": 1, "title": "x", "url": "https://example.com/video/thermostat-debate", "lib": 1},
    {"id": "k999", "title": "Old saved podcast", "creator": "Added by you", "type": "Podcast", "cat": "Culture", "url": "https://example.org/old-pod", "note": "from the old app", "rating": 5, "votes": 0, "lib": 1}]}

with sync_playwright() as p:
    br = p.chromium.launch(); iphone = p.devices["iPhone 13"]
    errors = []
    def page(ctx, who):
        pg = ctx.new_page(); pg.on("dialog", lambda d: d.accept()); pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); return pg
    def shot(pg, n):
        try: pg.screenshot(path=f"{SHOTS}/{n}.png", timeout=15000)
        except Exception as e: print("    (screenshot skipped)", n)
    phone = br.new_context(**iphone)
    phone.add_init_script("if(!sessionStorage.getItem('seeded')){localStorage.setItem('bridge_real_v1', %s);sessionStorage.setItem('seeded','1')}" % json.dumps(json.dumps(LEGACY)))
    paul = page(phone, "paul-phone")

    # 1) guest sign-up migrates the old device-local library into the account
    paul.goto(BASE); paul.click("#sbtn"); paul.fill("#nm", "SmokePaul"); paul.click("#nok")
    expect(paul.get_by_text("No clubs yet")).to_be_visible(timeout=T)
    paul.goto(BASE + "#profile"); expect(paul.locator(".card", has_text="Old saved podcast")).to_be_visible(timeout=T)
    expect(paul.locator(".card", has_text="Old saved podcast")).to_contain_text("from the old app")
    left = json.loads(paul.evaluate("localStorage.getItem('bridge_real_v1')"))["clips"]
    assert all(c.get("ex") for c in left), left
    step("Old device-local saved item migrated into the account on first load")
    paul_id = paul.evaluate("ME")

    # 2) add to library (link, category, note)
    paul.click("text=＋ Save a clip"); paul.fill("#aurl", "https://www.youtube.com/watch?v=lib-test"); paul.fill("#atitle", "A talk that changed my mind")
    paul.fill("#anote", "Made me rethink nuclear power."); shot(paul, "08-save-clip"); paul.click("#asave")
    expect(paul.get_by_text("Your note:")).to_be_visible(timeout=T); expect(paul.get_by_text("Made me rethink nuclear power.")).to_be_visible()
    shot(paul, "09-clip-detail"); paul.goto(BASE + "#profile"); expect(paul.locator(".list .card.tap")).to_have_count(2, timeout=T)
    step("Save a clip (link, title, note) saves online; Me shows 2 saved clips")

    # 3) start a bridge from a library item -> save-account prompt
    paul.locator(".card", has_text="A talk that changed my mind").click(); paul.click("text=Start a club with this")
    expect(paul.locator("#mclip")).to_have_value(re.compile(r"[0-9a-f-]{36}"), timeout=T)
    paul.fill("#mfriend", "SmokeSam"); paul.click("#mgo"); expect(paul.locator("#itxt")).to_be_visible(timeout=T)
    link = re.search(r"(https?://\S+#b/[0-9a-f]{32})", paul.locator("#itxt").input_value()).group(1)
    assert "A talk that changed my mind" in paul.locator("#itxt").input_value()
    expect(paul.locator("#savenote")).to_be_visible(); step("Club started from a saved clip; invite shows 'Save your account' prompt")

    # 4) save account: guest -> email with a 6-digit code (same user id, data kept)
    paul.click("#savenote a"); expect(paul.get_by_text("Save your account").first).to_be_visible(timeout=T)
    paul.fill("#em", PAUL_EMAIL); n0 = len(mails(PAUL_EMAIL)); paul.click("#esend")
    code, subj = new_code(PAUL_EMAIL, n0); assert "confirmation code" in subj, subj
    expect(paul.locator("#code")).to_be_visible(timeout=T); shot(paul, "10-save-account-code")
    paul.fill("#code", "000000"); paul.click("#cok"); expect(paul.locator("#emsg")).to_contain_text("wrong or expired", timeout=T); step("Wrong code shows a clear error")
    paul.fill("#code", code); paul.click("#cok")
    expect(paul.get_by_text(f"Signed in as {PAUL_EMAIL}")).to_be_visible(timeout=T)
    assert paul.evaluate("ME") == paul_id and paul.evaluate("USER.is_anonymous") is False
    step("Save your account: email code converts the guest in place (same user id, no longer anonymous)")

    # 5) Sam joins, opens Paul's library, adds an item from it to his own
    samc = br.new_context(**iphone); sam = page(samc, "sam")
    sam.goto(link); sam.fill("#jname", "SmokeSam"); sam.click("#jgo"); expect(sam.get_by_text("Answer three questions")).to_be_visible(timeout=T)
    sam.click(".steps button:has-text('Joined')"); sam.click("text=See SmokePaul's saved clips"); expect(sam.get_by_text("SmokePaul's saved clips").first).to_be_visible(timeout=T)
    expect(sam.locator(".card", has_text="A talk that changed my mind")).to_be_visible(timeout=T); expect(sam.locator(".card", has_text="Old saved podcast")).to_be_visible()
    shot(sam, "11-friend-saved-clips")
    sam.locator(".card", has_text="A talk that changed my mind").click(); expect(sam.get_by_text("SmokePaul's note:")).to_be_visible(timeout=T)
    sam.click("#addlib"); expect(sam.get_by_text("✓ Saved")).to_be_visible(timeout=T)
    sam.goto(BASE + "#profile"); expect(sam.locator(".card", has_text="A talk that changed my mind")).to_be_visible(timeout=T)
    step("Club partner sees your saved clips (with notes) and can save one to their own")

    # 6) Sam (guest) tries Paul's email -> 'already has an account'
    sam.goto(BASE + "#account"); sam.fill("#em", PAUL_EMAIL); sam.click("#esend")
    expect(sam.locator("#emsg")).to_contain_text("already has a Clip Club account", timeout=T); expect(sam.locator("#exists")).to_be_visible()
    step("Saving with an email that's taken -> clear message + option to switch")

    # 7) Paul on a NEW browser: 'I have an account' -> code -> bridges + library come back
    laptop = br.new_context(viewport={"width": 1100, "height": 800}); lap = page(laptop, "paul-laptop")
    lap.goto(BASE); lap.click("#lbtn"); lap.fill("#em", "nobody-" + PAUL_EMAIL); lap.click("#esend")
    expect(lap.locator("#emsg")).to_contain_text("No Clip Club account uses that email", timeout=T); step("Sign-in with an unknown email -> clear message (no account created)")
    lap.fill("#em", PAUL_EMAIL); n0 = len(mails(PAUL_EMAIL)); lap.click("#esend")
    code, subj = new_code(PAUL_EMAIL, n0); assert "sign-in code" in subj, subj
    shot(lap, "12-signin-code"); lap.fill("#code", code); lap.click("#cok")
    expect(lap.locator(".card", has_text="A talk that changed my mind")).to_contain_text("With SmokeSam", timeout=T)
    assert lap.evaluate("ME") == paul_id
    lap.goto(BASE + "#profile"); expect(lap.locator(".card", has_text="Old saved podcast")).to_be_visible(timeout=T)
    expect(lap.locator(".card", has_text="A talk that changed my mind")).to_be_visible(); expect(lap.locator("h1")).to_contain_text("SmokePaul")
    step("New browser: email-code sign-in restores the same account — clubs, saved clips, name")

    # 8) library syncs across Paul's two browsers
    lap.click("text=＋ Save a clip"); lap.fill("#aurl", "https://example.org/added-on-laptop"); lap.fill("#atitle", "Added on laptop"); lap.click("#asave")
    expect(lap.get_by_text("Your note:")).to_have_count(0, timeout=T)
    paul.goto(BASE + "#profile"); expect(paul.locator(".card", has_text="Added on laptop")).to_be_visible(timeout=T)
    step("Saved clips sync: clip saved on the laptop shows up on the phone")
    # a third device
    phone2 = br.new_context(**iphone); p2 = page(phone2, "paul-phone2"); p2.goto(BASE + "#signin"); p2.fill("#em", PAUL_EMAIL); n0 = len(mails(PAUL_EMAIL)); p2.click("#esend")
    code, _ = new_code(PAUL_EMAIL, n0); p2.fill("#code", code); p2.click("#cok"); expect(p2.locator(".card", has_text="With SmokeSam")).to_be_visible(timeout=T)
    p2.goto(BASE + "#profile"); expect(p2.locator(".card", has_text="Added on laptop")).to_be_visible(timeout=T); step("A third device signs in and sees the same clubs and saved clips")

    # 9) sign out (email user) and back in
    lap.goto(BASE + "#profile"); lap.click("#sout"); expect(lap.locator("#sbtn")).to_be_visible(timeout=T)
    step("Email user can sign out (and sign back in, as shown above)")
    assert not errors, errors; step("No uncaught JS errors")
    br.close()
print(f"\nE2E v2: {len(results)} checks passed")
