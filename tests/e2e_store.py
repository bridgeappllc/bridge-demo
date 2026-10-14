"""E2E for store requirements: legal pages + links, Report (message, user+block, library item),
and Settings > Delete account (the partner keeps the bridge, shown as "Deleted user").
  BASE=<app url> (default local). DB checks run only against the local stack (DSN reachable)."""
import os, re, time, uuid
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); LOCAL = "127.0.0.1" in BASE or "localhost" in BASE
HERE = os.path.dirname(os.path.abspath(__file__)); SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(HERE, "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 20000; tag = uuid.uuid4().hex[:4]; A, B = f"SmokeAva{tag}", f"SmokeBen{tag}"
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
    for pg, w in ((pa, "ava"), (pb, "ben")):
        pg.on("pageerror", lambda e, w=w: errors.append(f"{w}: {e}")); pg.on("dialog", lambda d: d.accept())
    shot = lambda pg, nm: pg.screenshot(path=f"{SHOTS}/{nm}.png")
    # legal pages + links
    pa.goto(BASE); expect(pa.locator("#sbtn")).to_be_visible(timeout=T)
    expect(pa.locator(".legal a")).to_have_count(3, timeout=T); hrefs = pa.locator(".legal a").evaluate_all("els=>els.map(e=>e.getAttribute('href'))")
    assert hrefs == ["privacy.html", "terms.html", "support.html"], hrefs
    for page, must in (("privacy.html", ["DRAFT", "not legal advice", "Delete account", "13", "Supabase", "Resend", "Google Fonts", "don't sell"]),
                       ("terms.html", ["DRAFT", "zero tolerance", "at least 13", "within 24 hours", "Hawaii"]), ("support.html", ["bridgeappllc@gmail.com", "Delete account"])):
        r = pa.request.get(BASE + page); assert r.ok, page; body = r.text()
        miss = [m for m in must if m not in body]; assert not miss, (page, miss)
    pa.goto(BASE + "privacy.html"); expect(pa.get_by_role("heading", name="Privacy Policy")).to_be_visible(); shot(pa, "st-01-privacy")
    pa.goto(BASE + "terms.html"); shot(pa, "st-02-terms"); pa.goto(BASE + "support.html"); shot(pa, "st-03-support")
    step("Privacy / Terms / Support pages load (marked DRAFT; 13+, zero tolerance, contact) and are linked from welcome")
    # sign up both
    def signup(pg, nm):
        pg.goto(BASE); pg.click("#sbtn"); expect(pg.locator("#agree")).to_be_visible()
        assert pg.locator("#agree a").evaluate_all("els=>els.map(e=>e.getAttribute('href'))") == ["terms.html", "privacy.html"]
        pg.fill("#nm", nm); pg.click("#nok"); expect(pg.get_by_text("Pick your topics")).to_be_visible(timeout=T); pg.click("text=Skip")
        expect(pg.get_by_text("Your Pods")).to_be_visible(timeout=T)
    signup(pa, A); shot(pa, "st-04-bridges"); signup(pb, B); step("Sign-up shows the 13+ / Terms / Privacy agreement with links")
    # bridge A -> B, both answer, B chats
    pa.goto(BASE + "#new"); pa.fill("#murl", "https://example.org/store-test"); pa.fill("#mtitle", "Store test episode"); pa.fill("#mfriend", B)
    pa.click("#mgo"); expect(pa.locator("#itxt")).to_be_visible(timeout=T)
    link = re.search(r"(https?://\S+#b/[0-9a-f]{32})", pa.locator("#itxt").input_value()).group(1)
    pb.goto(link); pb.fill("#jname", B); pb.click("#jgo"); expect(pb.get_by_text("Answer & rate")).to_be_visible(timeout=T)
    for pg in (pb, pa):
        if pg is pa: pa.click("#nx"); expect(pa.get_by_text("Answer & rate")).to_be_visible(timeout=T)
        pg.fill("#q3", f"{'Ben' if pg is pb else 'Ava'} answer takeaway"); pg.locator('.rate [data-rv="7"]').click()
        pg.click("#qsave"); expect(pg.get_by_text("💬 Talk")).to_be_visible(timeout=T)
    pb.fill("#ct", "Ben says hello"); pb.click("#cs"); expect(pb.locator(".bub.me")).to_have_text("Ben says hello", timeout=T)
    expect(pa.locator(".bub:not(.me)")).to_have_text("Ben says hello", timeout=T)
    assert pa.locator("button.rp[data-rep=message]").count() == 1 and pb.locator("button.rp[data-rep=message]").count() == 0
    step("Chat: a Report link appears under the other person's messages only")
    # report the message
    pa.click("button.rp[data-rep=message]"); expect(pa.locator("#repsheet")).to_be_visible()
    assert pa.locator("#rsend").is_disabled(); shot(pa, "st-05-report-sheet")
    pa.click("#repsheet label:has-text('Harassment')"); pa.fill("#rnote", "test note"); assert not pa.locator("#rsend").is_disabled()
    pa.click("#rsend"); expect(pa.locator(".toast")).to_have_text("Thanks — your report was sent", timeout=T); expect(pa.locator("#repsheet")).to_have_count(0)
    if db: assert q("select r.reason, r.note, r.snapshot from reports r join profiles p on p.id=r.reporter where p.display_name=%s and target_type='message'", (A,)) == [("harassment", "test note", "Ben says hello")]
    step("Report a chat message: pick a reason (+ optional note) -> stored privately with a snapshot")
    # B adds a library item; A reports it from B's library
    pb.goto(BASE + "#profile"); pb.click(".tabs button:has-text('Add')"); pb.fill("#aurl", "https://example.org/ben-item"); pb.fill("#atitle", "Ben's questionable item")
    pb.click("#asave"); expect(pb.locator(".toast")).to_be_visible(timeout=T)
    ben_id = pa.locator("a[href^='#u/']").first.get_attribute("href")[3:]
    pa.goto(BASE + f"#u/{ben_id}"); expect(pa.get_by_text("Ben's questionable item")).to_be_visible(timeout=T)
    pa.click("text=Ben's questionable item"); expect(pa.locator("#repi")).to_be_visible(timeout=T)
    pa.click("#repi"); pa.click("#repsheet label:has-text('Spam')"); pa.click("#rsend"); expect(pa.locator(".toast")).to_have_text("Thanks — your report was sent", timeout=T)
    if db:  # poll: the identical toast from the previous (message) report can still be on screen
        for _ in range(40):
            if q("select count(*) from reports r join profiles p on p.id=r.reporter where p.display_name=%s and target_type='library_item' and reason='spam'", (A,)) == [(1,)]: break
            time.sleep(0.25)
        else: raise AssertionError("library_item report not stored")
    step("Report an item in someone's library (from the item page)")
    # report the user + block
    pa.goto(BASE + f"#u/{ben_id}"); expect(pa.locator("#repu")).to_be_visible(timeout=T); shot(pa, "st-06-profile-report-block")
    pa.click("#repu"); expect(pa.locator("#rblock")).to_be_visible(); pa.click("#repsheet label:has-text('Pretending')"); pa.check("#rblock"); pa.click("#rsend")
    expect(pa.locator(".toast")).to_have_text("Thanks — reported and blocked", timeout=T)
    if db: assert q("select count(*) from reports r join profiles p on p.id=r.reporter where p.display_name=%s and target_type='user' and reason='impersonation'", (A,)) == [(1,)] \
        and q("select count(*) from blocks b join profiles p on p.id=b.blocker where p.display_name=%s", (A,)) == [(1,)]
    step("Report a person with 'Also block' -> report stored + person blocked")
    # B deletes their account
    if db: before_other = q("select count(*) from auth.users")[0][0]
    pb.goto(BASE + "#profile"); pb.click(".tabs button:has-text('Settings')"); expect(pb.locator("#delbtn")).to_be_visible(timeout=T)
    expect(pb.locator("a[href='privacy.html']")).to_be_visible(); pb.evaluate("document.querySelector('#delcard')?.scrollIntoView({block:'center'})"); shot(pb, "st-07-settings-delete")
    pb.click("#delbtn"); expect(pb.locator("#delc")).to_be_visible(); pb.fill("#delc", "nope"); pb.click("#delyes")
    expect(pb.locator(".toast")).to_have_text("Type DELETE to confirm"); pb.evaluate("document.querySelector('#delcard')?.scrollIntoView({block:'center'})"); shot(pb, "st-08-delete-confirm")
    pb.fill("#delc", "DELETE"); pb.click("#delyes"); expect(pb.locator("#sbtn")).to_be_visible(timeout=T)
    expect(pb.locator(".toast")).to_have_text("Your account and data were deleted"); shot(pb, "st-09-deleted")
    assert pb.evaluate("localStorage.getItem('bridge-auth')") is None
    if db:
        assert q("select count(*) from profiles where display_name=%s", (B,)) == [(0,)] and q("select count(*) from auth.users")[0][0] == before_other - 1
        assert q("select count(*) from library_items where user_id=%s", (ben_id,)) == [(0,)] and q("select count(*) from auth.users where id=%s", (ben_id,)) == [(0,)]
    step("Settings > Delete account: needs typed DELETE; deletes the account + data, signs out, back to welcome")
    pa.goto(BASE + "#bridges"); expect(pa.get_by_text("You & Deleted user")).to_be_visible(timeout=T); shot(pa, "st-10-bridges-deleted-user")
    pa.click("text=You & Deleted user"); pa.click(".steps button:has-text('Talk')")
    expect(pa.locator("#leftnote")).to_be_visible(timeout=T); assert pa.locator("#ct").count() == 0 and pa.locator(".bub").count() == 0
    shot(pa, "st-11-bridge-partner-left")
    if db: assert q("select count(*) from profiles where display_name=%s", (A,)) == [(1,)]
    step("Partner keeps the bridge: 'Deleted user', their messages gone, chat closed; partner's account untouched")
    assert not errors, errors; step("No uncaught JS errors")
    br.close()
print(f"\nE2E store: {n} checks passed")
