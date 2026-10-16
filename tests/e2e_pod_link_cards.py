"""E2E (LOCAL): compact link cards on the Pods page and inside pods. Duo pods and group pods show the clip as a compact
card (small 16:9 thumbnail, title, favicon + site), previews are cached on the pod rows (bridges / group_pod_clips) by
members and not refetched; non-members on the invite page never get the URL or a thumbnail. Library cards are compact
(thumbnail <=120px wide) and the item page uses the larger variant. 390px: no horizontal scroll."""
import os, time
from authflow import signup_email
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); assert "127.0.0.1" in BASE, "local only: sign-up sends code emails"
T = 30000; n = 0; tag = str(int(time.time()) % 100000)
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
FIX = BASE + "tests/fixtures/"; OG = FIX + "og-page.html?pod" + tag; YT = "https://youtu.be/dQw4w9WgXcQ?si=p" + tag
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
def poll(pg, js, arg=None, what="condition"):
    for _ in range(90):
        if pg.evaluate(js, arg): return
        pg.wait_for_timeout(500)
    raise AssertionError(what)
def thumbs_loaded(pg):
    poll(pg, "()=>[...document.querySelectorAll('.lth img')].every(i=>i.complete&&i.naturalWidth>0)", what="thumbnails never loaded")
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    ca, cb = br.new_context(viewport={"width": 1000, "height": 1300}), br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 390, "height": 844}})
    a, b = ca.new_page(), cb.new_page()
    for pg in (a, b): pg.on("pageerror", lambda e: errors.append(str(e))); pg.on("dialog", lambda d: d.accept())
    a.goto(BASE); assert a.evaluate("CFG.SUPABASE_URL") == "http://127.0.0.1:54321", "not the local stack"
    a.click("#sbtn"); signup_email(a, f"SmokePa{tag}"); expect(a.get_by_text("Pick your topics")).to_be_visible(timeout=T); a.click("text=Skip")
    b.goto(BASE); b.click("#sbtn"); signup_email(b, f"SmokePb{tag}"); expect(b.get_by_text("Pick your topics")).to_be_visible(timeout=T); b.click("text=Skip")
    bid = b.evaluate("USER.id")
    br1 = a.evaluate("async u=>(await sb.rpc('create_bridge',{p_display_name:PROFILE.display_name,p_clip_title:'Ocean episode',p_clip_url:u,p_clip_type:'Podcast',p_clip_cat:'Science',p_clip_creator:'',p_friend_label:'Ben',p_reward:''})).data", OG)
    br1 = br1[0] if isinstance(br1, list) else br1
    gid = a.evaluate("async id=>{const r=await sb.rpc('create_group_pod',{p_name:'Clip nerds',p_members:[id]});if(r.error)throw r.error;return r.data}", bid)
    a.evaluate("async([g,u])=>{const r=await sb.rpc('share_to_group_pod',{p_pod:g,p_title:'Rick video',p_url:u,p_kind:'Video',p_note:''});if(r.error)throw r.error}", [gid, YT])
    a.goto(BASE + "#bridges"); a.reload()
    duo = a.locator(".card", has_text="You & Ben").first; expect(duo.locator(".lc")).to_have_count(1, timeout=T)
    expect(duo.locator(".lc", has_text="Ocean episode").locator(".lsite")).to_contain_text("Ocean Pod", timeout=T)
    grp = a.locator(".gcard", has_text="Clip nerds"); expect(grp.locator('.lth img[src="https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg"]')).to_have_count(1, timeout=T)
    expect(grp.locator(".play")).to_have_count(1); step("Pods page: duo pod (og preview) and group pod (YouTube) show compact link cards")
    poll(a, "async id=>(await sb.from('bridges').select('preview_at,thumb_url,preview_site').eq('id',id).single()).data.preview_at", br1["id"], "duo preview not cached")
    poll(a, "async g=>(await sb.from('group_pod_clips').select('preview_at').eq('pod_id',g)).data.every(x=>x.preview_at)", gid, "group clip preview not cached")
    row = a.evaluate("async id=>(await sb.from('bridges').select('thumb_url,preview_site').eq('id',id).single()).data", br1["id"])
    assert row["preview_site"] == "Ocean Pod" and row["thumb_url"].endswith("hqdefault.jpg"), row; step("Previews cached on bridges / group_pod_clips rows")
    w = duo.locator(".lth").evaluate("e=>e.getBoundingClientRect().width"); assert 90 <= w <= 122, w; step(f"Compact thumbnail ({w:.0f}px wide)")
    calls = []; a.on("request", lambda r: calls.append(r.url) if "/functions/v1/link-preview" in r.url else None)
    a.reload(); expect(a.locator(".card", has_text="You & Ben").first.locator(".lc")).to_have_count(1, timeout=T); a.wait_for_timeout(1500); assert not calls, calls; step("Reload: no refetch")
    with ca.expect_page() as pi: a.locator(".card", has_text="You & Ben").first.locator(".lth").click()
    pi.value.close(); assert a.url.endswith("#bridges"), a.url; step("Clicking the card opens the link in a new tab (doesn't navigate the pod card)")
    a.locator(".card", has_text="You & Ben").first.locator(".ti", has_text="You & Ben").click(); expect(a.locator(".lc", has_text="Ocean episode")).to_have_count(1, timeout=T); step("Duo pod view shows the card")
    a.goto(BASE + "#pod/" + gid); expect(a.locator(".gclip .lc", has_text="Rick video")).to_have_count(1, timeout=T); step("Group pod view shows the card")
    # B: non-member of the duo pod opens the invite page -> no URL, no thumbnail
    b.goto(BASE + "#b/" + br1["invite_token"]); expect(b.locator("#lockl")).to_be_visible(timeout=T)
    assert b.locator(".lc").count() == 0 and b.locator("img[src*='youtube'], img[src*='hqdefault']").count() == 0 and OG not in b.content()
    pv = b.evaluate("async t=>(await sb.rpc('preview_bridge_v2',{p_token:t})).data", br1["invite_token"])
    assert not any(k in (pv[0] if pv else {}) for k in ("thumb_url", "preview_title", "preview_site")) and not (pv[0] or {}).get("clip_url"), pv
    leak = b.evaluate("async id=>(await sb.from('bridges').select('clip_url,thumb_url').eq('id',id)).data", br1["id"]); assert leak == [], leak
    step("Invite page (non-member): no URL, no thumbnail, preview RPC and table don't return them")
    b.goto(BASE + "#bridges"); b.reload(); g2 = b.locator(".gcard", has_text="Clip nerds"); expect(g2.locator(".lth img")).to_have_count(1, timeout=T)
    thumbs_loaded(b); assert b.evaluate("document.documentElement.scrollWidth") <= 390
    b.screenshot(path=f"{SHOTS}/plc-pods-mobile.png", full_page=True); step("Group member sees the card on Pods at 390px, no horizontal scroll")
    assert not errors, errors; step("No JS errors"); br.close()
print(f"E2E pod link cards: {n} checks passed")
