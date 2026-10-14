"""Hosted-safe smoke for the share card (no email): link-preview meta + og:image on BASE, invite text has no clip URL,
invite landing shows the title but not the clip URL (page + API) to a visitor. 1 Smoke email account via hosted_users."""
import io, os, re, time, urllib.request
from hosted_users import make, confirm
from playwright.sync_api import sync_playwright, expect
from PIL import Image
BASE = os.environ["BASE"]; T = 30000; n = 0; tag = str(int(time.time()) % 100000); URL = f"https://example.org/secret-{tag}"; SHOTS = os.environ.get("SHOTS_DIR", "/tmp/shots-share"); os.makedirs(SHOTS, exist_ok=True)
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
html = urllib.request.urlopen(BASE + f"?nc={tag}").read().decode(); meta = dict(re.findall(r'<meta (?:property|name)="([^"]+)" content="([^"]*)"', html))
assert meta["og:url"] == BASE and meta["og:image"] == BASE + "assets/og-image.png" and meta["twitter:image"] == meta["og:image"] and meta["twitter:card"] == "summary_large_image", meta
assert meta["og:title"] == "Pod Club" and meta["og:description"] == "Share it with your pod."
im = Image.open(io.BytesIO(urllib.request.urlopen(meta["og:image"]).read())); assert im.size == (1200, 630), im.size
assert urllib.request.urlopen(BASE + "assets/apple-touch-icon.png").status == 200; step(f"Meta + og:image ({meta['og:image']}, 1200x630) + apple-touch-icon served")
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    def phone(who):
        pg = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}}).new_page(); pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); return pg
    a = phone("A"); ia = make(a, BASE, f"SmokeSha{tag}"); confirm(BASE, [(a, ia)])
    r = a.evaluate("async([u,t])=>{const{data,error}=await sb.rpc('create_bridge',{p_display_name:PROFILE.display_name,p_clip_title:t,p_clip_url:u,p_clip_type:'Podcast',p_clip_cat:'',p_clip_creator:'',p_friend_label:'',p_reward:''});if(error)throw error;return data[0]||data}", [URL, f"Smoke share {tag}"])
    a.goto(BASE + f"#bridge/{r['id']}/0"); txt = a.locator("#itxt").input_value(timeout=T)
    assert txt == f'Check this out: "Smoke share {tag}" — listen and let\'s talk about it on Pod Club: {BASE}#b/{r["invite_token"]}', txt
    a.screenshot(path=f"{SHOTS}/p-invite.png"); step("Invite text: title + Pod Club link only")
    v = phone("V"); bodies = []; v.on("response", lambda x: bodies.append(x.text()) if "/rest/v1/" in x.url else None)
    v.goto(BASE + "#b/" + r["invite_token"]); expect(v.get_by_text(f"Smoke share {tag}")).to_be_visible(timeout=T); expect(v.locator("#lockl")).to_be_visible(); v.wait_for_timeout(800)
    assert URL not in v.content() and not [b for b in bodies if URL in b]; v.screenshot(path=f"{SHOTS}/p-landing.png"); step("Invite landing: title only, clip URL not in page or API")
    assert not errors, errors; step("No JS errors"); br.close()
print(f"Hosted share smoke: {n} checks passed")
