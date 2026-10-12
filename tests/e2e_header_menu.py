"""E2E: header name menu (My profile / Settings / Sign out, a11y, outside tap + Escape close) and logo -> home."""
import os, re
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); SHOT = os.environ.get("MENU_SHOT")
T = 20000; n = 0
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
with sync_playwright() as p:
    br = p.chromium.launch(); pg = br.new_context(**p.devices["iPhone SE"]).new_page()
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    dlg = {"accept": False, "msgs": []}
    pg.on("dialog", lambda d: (dlg["msgs"].append(d.message), d.accept() if dlg["accept"] else d.dismiss()))
    pg.goto(BASE); home = pg.locator("#home"); home.click(); expect(pg.locator("#sbtn")).to_be_visible(); step("Signed out: logo stays on Welcome")
    pg.click("#sbtn"); pg.fill("#nm", "SmokeMenu"); pg.click("#nok"); [pg.click(f".topic[data-t={t}]") for t in ("Politics", "Science", "Culture")]; pg.click("#tgo")
    ub = pg.locator("#ubtn"); expect(ub).to_contain_text("Hi, SmokeMenu", timeout=T); expect(ub).to_have_attribute("aria-expanded", "false")
    ub.click(); m = pg.locator("#umenu"); expect(m).to_be_visible(); expect(ub).to_have_attribute("aria-expanded", "true")
    expect(m.get_by_role("menuitem")).to_have_text(["My profile", "Settings", re.compile("Sign out")])
    bx = m.bounding_box(); vw = pg.viewport_size["width"]; assert bx["x"] >= 0 and bx["x"] + bx["width"] <= vw, (bx, vw)
    assert m.evaluate("e=>getComputedStyle(e).borderTopColor") == "rgb(29, 78, 216)"
    if SHOT: pg.screenshot(path=SHOT)
    step("Name button opens an on-screen Harbor Blue menu (aria-expanded, 3 items) at 375px")
    pg.keyboard.press("Escape"); expect(m).to_have_count(0); expect(ub).to_be_focused(); step("Escape closes and returns focus")
    ub.click(); pg.mouse.click(150, 400); expect(m).to_have_count(0); expect(ub).to_have_attribute("aria-expanded", "false"); step("Outside tap closes")
    ub.click(); m.get_by_text("My profile").click(); expect(pg).to_have_url(re.compile("#profile")); expect(pg.locator("h1")).to_contain_text("SmokeMenu", timeout=T); step("My profile opens the profile")
    pg.locator("#ubtn").click(); pg.locator("#umenu").get_by_text("Settings").click(); expect(pg.locator("#sout")).to_be_visible(timeout=T); step("Settings opens Profile > Settings")
    home.click(); expect(pg).to_have_url(re.compile("#bridges")); expect(pg.get_by_text("Your Clubs")).to_be_visible(timeout=T); step("Logo goes to Your Clubs when signed in")
    pg.locator("#ubtn").click(); pg.locator("#umenu").get_by_text("Sign out").click(); pg.wait_for_timeout(400)
    assert "guest" in dlg["msgs"][-1].lower(); expect(pg.locator("#ubtn")).to_be_visible(); step("Sign out (guest) shows the save-first warning; Cancel keeps you in")
    dlg["accept"] = True; pg.locator("#ubtn").click(); pg.locator("#umenu").get_by_text("Sign out").click(); expect(pg.locator("#lbtn")).to_be_visible(timeout=T)
    expect(pg.locator("#ubtn")).to_have_count(0); step("Confirmed sign-out from the menu lands on Welcome")
    assert not errors, errors; step("No uncaught JS errors")
    br.close()
print(f"E2E header menu: {n} checks passed")
