"""E2E for the content filter: friendly inline errors ("Please keep it respectful") for names, @usernames and bios;
chat/library profanity masked with ***; slurs blocked; server enforcement still works if the client list is missing.
  BASE=<app url> (default local). DB checks run only against the local stack."""
import os, re, uuid
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); LOCAL = "127.0.0.1" in BASE or "localhost" in BASE
HERE = os.path.dirname(os.path.abspath(__file__)); SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(HERE, "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 20000; tag = uuid.uuid4().hex[:4]; A, B = f"SmokeFay{tag}", f"SmokeFin{tag}"
R = "Please keep it respectful"
db = None
if LOCAL:
    import psycopg; db = psycopg.connect(os.environ.get("DSN", "postgresql://postgres@127.0.0.1:54322/postgres"), autocommit=True)
q = lambda sql, p=(): db.execute(sql, p).fetchall()
n = 0
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
with sync_playwright() as p:
    br = p.chromium.launch(); dev = p.devices["iPhone 13"]; errors = []
    ac, bc = br.new_context(**dev), br.new_context(**dev); pa, pb = ac.new_page(), bc.new_page()
    for pg, w in ((pa, "fay"), (pb, "fin")):
        pg.on("pageerror", lambda e, w=w: errors.append(f"{w}: {e}")); pg.on("dialog", lambda d: d.accept())
    shot = lambda pg, nm: pg.screenshot(path=f"{SHOTS}/{nm}.png")
    ierr = lambda pg: pg.locator(".ierr")
    # 1. sign-up name: inline error before any account is created
    pa.goto(BASE); expect(pa.locator("#sbtn")).to_be_visible(timeout=T)
    pa.wait_for_function("MOD.t&&MOD.t.length>10", timeout=T)
    pa.click("#sbtn"); pa.fill("#nm", "Sh1t Head"); pa.click("#nok")
    expect(ierr(pa)).to_contain_text(R, timeout=T); expect(pa.locator("#nm")).to_have_attribute("aria-invalid", "true"); shot(pa, "fl-01-signup-name")
    assert pa.evaluate("ME") is None, "no account should be created for a rejected name"
    pa.fill("#nm", A); expect(ierr(pa)).to_have_count(0)
    pa.click("#nok"); expect(pa.get_by_text("Pick your topics")).to_be_visible(timeout=T); pa.click("text=Skip"); expect(pa.get_by_text("Your Pods")).to_be_visible(timeout=T)
    step("Sign-up: a profane name gets an inline 'Please keep it respectful' (no account created); the error clears when typing")
    # 2. settings: name, @username, bio
    pa.goto(BASE + "#profile"); pa.click(".tabs button:has-text('Settings')"); expect(pa.locator("#pname")).to_be_visible(timeout=T)
    pa.fill("#pname", "B!tch"); pa.click("#psave"); expect(ierr(pa)).to_contain_text(R, timeout=T)
    pa.fill("#pname", A); expect(ierr(pa)).to_have_count(0)
    pa.fill("#puser", f"fuck_{tag}"); pa.click("#pubsave"); expect(ierr(pa)).to_contain_text("@username", timeout=T); shot(pa, "fl-02-username")
    pa.fill("#puser", f"smokefay{tag}"); pa.fill("#pbio", "Podcasts, bullshit and more"); pa.click("#pubsave"); expect(ierr(pa)).to_contain_text("bio", timeout=T)
    pa.fill("#pbio", "Classic cocktails in Scunthorpe"); pa.click("#pubsave"); expect(pa.locator(".toast")).to_have_text("Profile saved", timeout=T)
    step("Settings: profane name / @username / bio each get an inline error; Scunthorpe-style bio saves fine")
    # 3. server still enforces when the client list is missing (e.g. couldn't load)
    pa.click(".tabs button:has-text('Settings')"); expect(pa.locator("#pbio")).to_be_visible(timeout=T)
    pa.evaluate("MOD.t=null;localStorage.removeItem('bridge_mod_v1')"); pa.fill("#pbio", "total shit"); pa.click("#pubsave")
    expect(ierr(pa)).to_contain_text(R, timeout=T); shot(pa, "fl-03-server-enforced")
    pa.wait_for_function("MOD.t&&MOD.t.length>10", timeout=T)
    if db: assert q("select bio from profiles where display_name=%s", (A,)) == [("Classic cocktails in Scunthorpe",)]
    step("Without the client list the server rejects it and the app still shows the friendly inline message (and reloads the list)")
    # 4. second user with a pod; chat masking + slur blocking
    pb.goto(BASE); pb.click("#sbtn"); pb.fill("#nm", B); pb.click("#nok"); expect(pb.get_by_text("Pick your topics")).to_be_visible(timeout=T); pb.click("text=Skip")
    pa.goto(BASE + "#new"); pa.fill("#murl", "https://example.org/filter-test"); pa.fill("#mtitle", "Filter test"); pa.fill("#mfriend", B)
    pa.click("#mgo"); expect(pa.locator("#itxt")).to_be_visible(timeout=T)
    link = re.search(r"(https?://\S+#b/[0-9a-f]{32})", pa.locator("#itxt").input_value()).group(1)
    pb.goto(link); pb.fill("#jname", "Dickhead"); pb.click("#jgo"); expect(ierr(pb)).to_contain_text(R, timeout=T)
    pb.fill("#jname", B); pb.click("#jgo"); expect(pb.get_by_text("Answer three questions")).to_be_visible(timeout=T)
    step("Joining a pod with a profane name is stopped inline")
    pb.locator(".q").nth(0).fill("Honestly, kys"); pb.locator(".q").nth(1).fill("okay then"); pb.locator(".q").nth(2).fill("fine by me")
    pb.click("#qsave"); expect(ierr(pb)).to_contain_text(R, timeout=T)
    pb.locator(".q").nth(0).fill("It was fucking great"); pb.click("#qsave"); expect(pb.get_by_text("💬 Talk")).to_be_visible(timeout=T)
    pa.click("#nx"); expect(pa.get_by_text("Answer three questions")).to_be_visible(timeout=T)
    for i in range(3): pa.locator(".q").nth(i).fill(f"Fay answer {i}")
    pa.click("#qsave"); expect(pa.get_by_text("💬 Talk")).to_be_visible(timeout=T)
    pa.click("button:has-text('Answer')"); expect(pa.get_by_text("It was f****** great")).to_be_visible(timeout=T); pa.click("button:has-text('Talk')")
    step("Answers: a slur is blocked inline; profanity is saved masked (partner sees 'f******')")
    pb.fill("#ct", "That was some sh!t, wow"); pb.click("#cs"); expect(pb.locator(".bub.me")).to_have_text("That was some s***, wow", timeout=T)
    expect(pb.locator(".toast")).to_contain_text("hidden", timeout=T); expect(pa.locator(".bub:not(.me)")).to_have_text("That was some s***, wow", timeout=T)
    pb.fill("#ct", "shut up you f4ggot"); pb.click("#cs"); expect(ierr(pb)).to_contain_text(R, timeout=T); shot(pb, "fl-04-chat")
    expect(pb.locator(".bub.me")).to_have_count(1); expect(pb.locator("#ct")).to_have_value("shut up you f4ggot")
    pb.fill("#ct", "Scunthorpe has classic cocktails"); expect(ierr(pb)).to_have_count(0); pb.click("#cs")
    expect(pb.locator(".bub.me").last).to_have_text("Scunthorpe has classic cocktails", timeout=T)
    if db: assert [r[0] for r in q("select m.body from messages m join profiles p on p.id=m.user_id where p.display_name=%s order by m.id", (B,))] == ["That was some s***, wow", "Scunthorpe has classic cocktails"]
    step("Chat: profanity is masked for both people (with a 'hidden' note), slurs are blocked inline and not sent, Scunthorpe untouched")
    # 5. library title/note masked
    pa.goto(BASE + "#profile"); pa.click(".tabs button:has-text('Add')"); pa.fill("#aurl", f"https://example.org/fl-{tag}")
    pa.fill("#atitle", "Wetback stories"); pa.click("#asave"); expect(ierr(pa)).to_contain_text(R, timeout=T)
    pa.fill("#atitle", "Holy shit, what a show"); pa.fill("#anote", "This bitch of a week"); pa.click("#asave")
    expect(pa.get_by_text("Holy s***, what a show").first).to_be_visible(timeout=T); expect(pa.get_by_text("This b**** of a week").first).to_be_visible(timeout=T); shot(pa, "fl-05-library")
    step("Library: slur in a title is blocked inline; profanity in title/note is saved masked")
    assert not errors, errors; step("No uncaught JS errors")
    br.close()
print(f"E2E filter: {n} checks passed")
