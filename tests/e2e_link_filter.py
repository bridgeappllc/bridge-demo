"""E2E (LOCAL): adult / shortener links get the friendly inline error in the library and new-pod forms, the server
refuses them even if the client check is bypassed, and normal links still save."""
import os, time
from authflow import signup_email
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); assert "127.0.0.1" in BASE, "local only: sign-up sends code emails"
T = 30000; n = 0; tag = str(int(time.time()) % 100000); MSG = "That link can't be shared on Pod Club."
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    c = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}})
    a = c.new_page(); a.on("pageerror", lambda e: errors.append(str(e))); a.on("dialog", lambda d: d.accept())
    a.goto(BASE); a.click("#sbtn"); signup_email(a, f"SmokeLf{tag}"); expect(a.get_by_text("Pick your topics")).to_be_visible(timeout=T); a.click("text=Skip")
    a.goto(BASE + "#profile"); a.locator("[data-pt='Add']").first.click(); a.fill("#aurl", "https://www.PornHub.com/view_video.php?x=1"); a.fill("#atitle", f"Bad {tag}")
    a.click("#asave"); expect(a.locator(".ierr", has_text=MSG)).to_be_visible(timeout=T)
    assert a.evaluate("async()=>(await sb.from('library_items').select('id').eq('user_id',USER.id)).data.length") == 0
    a.screenshot(path=f"{SHOTS}/lf-1-library.png"); step("Library: adult link -> inline 'can't be shared', nothing saved")
    a.fill("#aurl", "https://open.spotify.com/episode/lf" + tag); a.fill("#atitle", f"Good {tag}"); a.click("#asave")
    a.wait_for_function("async()=>(await sb.from('library_items').select('id').eq('user_id',USER.id)).data.length===1", timeout=T); step("Library: normal link saves")
    expect(a.get_by_text("Remove from Library")).to_be_visible(timeout=T); a.goto(BASE + "#new"); a.select_option("#mclip", ""); a.fill("#murl", "bit.ly/3xyz"); a.locator("#mgo").click(); expect(a.locator(".ierr", has_text=MSG)).to_be_visible(timeout=T)
    a.screenshot(path=f"{SHOTS}/lf-2-newpod.png"); step("New pod: URL shortener -> inline error")
    e = a.evaluate("async()=>{const{error}=await sb.rpc('create_bridge',{p_display_name:PROFILE.display_name,p_clip_title:'x',p_clip_url:'https://m.xvideos.com/v',p_clip_type:'Video',p_clip_cat:'',p_clip_creator:'',p_friend_label:'',p_reward:''});return error}")
    assert e and e["code"] == "23514" and e["message"] == MSG and "link_filter:adult" in (e.get("details") or ""), e
    a.evaluate("fail({code:'23514',message:\"That link can't be shared on Pod Club.\",details:'link_filter:adult:clip_url'})"); expect(a.get_by_text(MSG).last).to_be_visible(timeout=T)
    step("Bypassing the client: server refuses (23514, friendly message) and fail() toasts it")
    assert a.evaluate("async()=>(await sb.rpc('link_ok',{p_url:'https://www.youtube.com/watch?v=1'})).data") is True; step("link_ok allows mainstream links")
    assert not errors, errors; step("No JS errors"); br.close()
print(f"E2E link filter: {n} checks passed")
