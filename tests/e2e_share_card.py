"""E2E (LOCAL): shares only invite people into the app — no raw clip URL in invite/resend/profile share text, the
invite landing hides the clip link until you've joined (title shows), and link-preview meta + og:image are present."""
import os, re, time, urllib.request
from authflow import signup_email, join_email
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); assert "127.0.0.1" in BASE, "local only: sign-up sends code emails"
T = 30000; n = 0; tag = str(int(time.time()) % 100000); URL = f"https://example.org/secret-clip-{tag}"
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    def phone(who):
        c = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}})
        c.add_init_script("window.__shared=[];navigator.share=t=>{window.__shared.push(t.text||t.url);return Promise.resolve()}")
        pg = c.new_page(); pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); pg.on("dialog", lambda d: d.accept()); return pg
    # meta / og image
    html = urllib.request.urlopen(BASE).read().decode()
    meta = dict(re.findall(r'<meta (?:property|name)="([^"]+)" content="([^"]*)"', html))
    assert meta["og:title"] == "Pod Club" and meta["og:description"] == "Share it with your pod." and meta["twitter:card"] == "summary_large_image", meta
    assert meta["og:image"].startswith("https://") and meta["og:image"].endswith("/assets/og-image.png") and meta["og:url"].startswith("https://"), meta
    assert 'rel="apple-touch-icon" sizes="180x180"' in html
    from PIL import Image; import io
    im = Image.open(io.BytesIO(urllib.request.urlopen(BASE + "assets/og-image.png").read())); assert im.size == (1200, 630) and im.format == "PNG", im.size
    step("Open Graph + Twitter meta (absolute og:image 1200x630 PNG, og:url), apple-touch-icon 180")
    a = phone("A"); a.goto(BASE); a.click("#sbtn"); signup_email(a, f"SmokeSia{tag}"); expect(a.get_by_text("Pick your topics")).to_be_visible(timeout=T); a.click("text=Skip")
    a.goto(BASE + "#new"); a.fill("#murl", URL) if a.locator("#murl").count() else None
    r = a.evaluate("async([u,t])=>{const{data,error}=await sb.rpc('create_bridge',{p_display_name:PROFILE.display_name,p_clip_title:t,p_clip_url:u,p_clip_type:'Podcast',p_clip_cat:'',p_clip_creator:'',p_friend_label:'',p_reward:''});if(error)throw error;return data[0]||data}", [URL, f"Secret clip {tag}"])
    a.goto(BASE + f"#bridge/{r['id']}/0"); txt = a.locator("#itxt").input_value(timeout=T)
    exp = f'Check this out: "Secret clip {tag}" — listen and let\'s talk about it on Pod Club: {BASE}#b/{r["invite_token"]}'
    assert txt == exp, (txt, exp); assert URL not in txt and "example.org" not in txt
    a.click("#rsi"); sh = a.evaluate("window.__shared.at(-1)"); assert sh == exp, sh
    a.screenshot(path=f"{SHOTS}/sc-1-invite.png"); step("Invite + Resend invite text: title + Pod Club link only, no clip URL")
    a.goto(BASE + "#people"); a.locator("#shme, #shme2").first.click(); sh = a.evaluate("window.__shared.at(-1)")
    assert sh.startswith(f"SmokeSia{tag} is on Pod Club: ") and "example.org" not in sh and BASE in sh, sh; step("Profile share: just the Pod Club profile link")
    v = phone("V"); bodies = []; v.on("response", lambda resp: bodies.append(resp.text()) if "/rest/v1/" in resp.url else None)
    v.goto(BASE + "#b/" + r["invite_token"]); expect(v.get_by_text(f"Secret clip {tag}")).to_be_visible(timeout=T); expect(v.locator("#lockl")).to_be_visible()
    assert v.get_by_text("Open link").count() == 0 and URL not in v.content(); v.wait_for_timeout(500); assert not [b for b in bodies if URL in b], "clip URL leaked to the invite page"
    v.screenshot(path=f"{SHOTS}/sc-2-landing.png"); step("Invite landing: title shows, clip URL not in the page or any API response")
    join_email(v, f"SmokeVic{tag}"); expect(v.get_by_text("Answer & rate")).to_be_visible(timeout=T)
    v.goto(BASE + f"#bridge/{r['id']}/1"); expect(v.locator(f"a[href='{URL}']").first).to_be_visible(timeout=T); step("After signing up + joining, the clip link is available")
    w = a.evaluate("document.documentElement.scrollWidth"); assert w <= 375, w
    assert not errors, errors; step("No overflow, no JS errors"); br.close()
print(f"E2E share card: {n} checks passed")
