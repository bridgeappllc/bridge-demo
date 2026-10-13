"""E2E: Profile > Settings > Sign out. Guest gets a 'save your account first' warning (cancel keeps
the account), email user gets a simple confirm; sign-out clears local app state and lands on Welcome,
then 'I Have an Account' sign-in and a fresh sign-up both work. Local stack (Mailpit) only."""
import json, os, re, time, urllib.request, urllib.parse
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); MAILPIT = os.environ.get("MAILPIT", "http://127.0.0.1:8025")
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 20000; n = 0
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
def mails(a): return json.load(urllib.request.urlopen(f"{MAILPIT}/api/v1/search?query=to:{urllib.parse.quote(a)}"))["messages"]
def code_for(a, before):
    for _ in range(40):
        m = mails(a)
        if len(m) > before: return re.search(r"(\d{6,10})", m[0]["Subject"]).group(1)
        time.sleep(0.5)
    raise AssertionError("no email")
EMAIL = f"smoke-out-{int(time.time())}@test.local"
with sync_playwright() as p:
    br = p.chromium.launch(); ctx = br.new_context(**p.devices["iPhone 13"]); pg = ctx.new_page()
    errors = []; pg.on("pageerror", lambda e: errors.append(str(e)))
    dlg = {"accept": True, "msgs": []}
    def on_dialog(d): dlg["msgs"].append(d.message); d.accept() if dlg["accept"] else d.dismiss()
    pg.on("dialog", on_dialog)
    def settings(): pg.get_by_text("Profile", exact=True).last.click(); pg.click("[data-pt=Settings]"); expect(pg.locator("#sout")).to_be_visible(timeout=T)
    def signup(name, topics=("Science", "Economics", "Education")):
        pg.click("#sbtn"); pg.fill("#nm", name); pg.click("#nok"); expect(pg.get_by_text("Pick your topics")).to_be_visible(timeout=T)
        [pg.click(f".topic[data-t={t}]") for t in topics]; pg.click("#tgo")
    pg.goto(BASE); signup("SmokeGuest", ("Politics", "Culture", "Science")); settings()
    btn = pg.locator("#sout"); expect(btn).to_have_text(re.compile("Sign out"))
    assert btn.evaluate("e=>getComputedStyle(e).color") == "rgb(74, 107, 87)", btn.evaluate("e=>getComputedStyle(e).color")
    pg.screenshot(path=f"{SHOTS}/signout.png", full_page=True); step("Settings shows a Harbor Blue 'Sign out' button")
    dlg["accept"] = False; btn.click(); pg.wait_for_timeout(500)
    assert "guest" in dlg["msgs"][-1].lower() and "save your account" in dlg["msgs"][-1].lower(), dlg["msgs"]
    expect(pg.locator("#sout")).to_be_visible(); step("Guest: warning suggests saving the account first; Cancel keeps you signed in")
    pg.click("#gosave"); pg.fill("#em", EMAIL); n0 = len(mails(EMAIL)); pg.click("#esend"); pg.fill("#code", code_for(EMAIL, n0)); pg.click("#cok")
    expect(pg.get_by_text("Account saved")).to_be_visible(timeout=T); settings(); expect(pg.get_by_text(EMAIL)).to_be_visible()
    dlg["accept"] = True; pg.click("#sout"); expect(pg.locator("#lbtn")).to_be_visible(timeout=T)
    assert "guest" not in dlg["msgs"][-1].lower(), dlg["msgs"][-1]
    st = pg.evaluate("localStorage.getItem('bridge_real_v1')"); assert "Politics" not in (st or ""), st
    assert pg.evaluate("(async()=>!(await sb.auth.getSession()).data.session)()")
    step("Email user: simple confirm, session ended, local state cleared, back on Welcome")
    pg.click("#lbtn"); pg.fill("#em", EMAIL); n0 = len(mails(EMAIL)); pg.click("#esend"); pg.fill("#code", code_for(EMAIL, n0)); pg.click("#cok")
    pg.wait_for_timeout(1500); pg.get_by_text("Profile", exact=True).last.click(); expect(pg.locator("h1")).to_contain_text("SmokeGuest", timeout=T)
    expect(pg.locator("p.mut.sm").first).to_contain_text("Politics", timeout=T); step("'I Have an Account' sign-in restores the same account after sign-out")
    settings(); pg.click("#sout"); expect(pg.locator("#sbtn")).to_be_visible(timeout=T)
    signup("SmokeFresh"); pg.get_by_text("Profile", exact=True).last.click(); expect(pg.locator("h1")).to_contain_text("SmokeFresh", timeout=T)
    expect(pg.locator("p.mut.sm").first).not_to_contain_text("Politics"); step("Fresh sign-up after sign-out gets a new, clean account")
    assert not errors, errors; step("No uncaught JS errors")
    br.close()
print(f"E2E signout: {n} checks passed")
