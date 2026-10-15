"""Hosted-safe smoke for the link filter (no email): adult/shortener links get the inline error in library + new pod,
the server refuses a bypass, a normal link saves. 1 Smoke account via hosted_users."""
import os, time
from hosted_users import make, confirm
from playwright.sync_api import sync_playwright, expect
BASE = os.environ["BASE"]; T = 30000; n = 0; tag = str(int(time.time()) % 100000); MSG = "That link can't be shared on Pod Club."
SHOTS = os.environ.get("SHOTS_DIR", "/tmp/shots-link"); os.makedirs(SHOTS, exist_ok=True)
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    a = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}}).new_page(); a.on("pageerror", lambda e: errors.append(str(e)))
    ia = make(a, BASE, f"SmokeLnk{tag}"); confirm(BASE, [(a, ia)])
    a.goto(BASE + "#profile"); a.wait_for_timeout(1500); a.locator("[data-pt='Add']").first.click(); a.fill("#aurl", "https://WWW.PornHub.com/x"); a.fill("#atitle", f"Bad {tag}"); a.click("#asave")
    expect(a.locator(".ierr", has_text=MSG)).to_be_visible(timeout=T); a.screenshot(path=f"{SHOTS}/link-library.png"); step("Library: adult link -> inline error")
    a.fill("#aurl", f"https://open.spotify.com/episode/smoke{tag}"); a.fill("#atitle", f"Good {tag}"); a.click("#asave"); expect(a.get_by_text("Remove from Library")).to_be_visible(timeout=T); step("Library: normal link saves")
    a.goto(BASE + "#new"); a.select_option("#mclip", ""); a.fill("#murl", "https://bit.ly/3xyz"); a.locator("#mgo").click(); expect(a.locator(".ierr", has_text=MSG)).to_be_visible(timeout=T)
    a.screenshot(path=f"{SHOTS}/link-newpod.png"); step("New pod: shortener -> inline error")
    e = a.evaluate("async()=>{const{error}=await sb.from('library_items').insert({user_id:USER.id,url:'https://m.xvideos.com/v',title:'x'});return error}")
    assert e and e["code"] == "23514" and e["message"] == MSG, e; step("Server refuses a client bypass (23514)")
    assert not errors, errors; step("No JS errors"); br.close()
print(f"Smoke link filter: {n} checks passed")
