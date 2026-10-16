"""E2E (LOCAL): Library items render as rich link cards — YouTube thumbnails (watch?v=, youtu.be, shorts, m.youtube),
og:image/og:title via the link-preview edge function (cached on the row, not refetched), Sage fallback tile when there
is no image or the image host is blocked, favicon + site name, play overlay; the card opens the URL in a new tab and
"Details" still opens the item page. Also the clip detail page shows the card."""
import os, time
from authflow import signup_email
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); assert "127.0.0.1" in BASE, "local only: sign-up sends code emails"
T = 30000; n = 0; tag = str(int(time.time()) % 100000)
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
FIX = BASE + "tests/fixtures/"
ITEMS = [("https://www.youtube.com/watch?v=aqz-KE-bpKQ&t=3", "Big Buck Bunny", "aqz-KE-bpKQ"), ("https://youtu.be/dQw4w9WgXcQ?si=abc", "Short link", "dQw4w9WgXcQ"),
         ("https://youtube.com/shorts/Oos4ojutOMM", "A short", "Oos4ojutOMM"), ("https://m.youtube.com/watch?feature=share&v=FEUjcRWfu3c", "Mobile link", "FEUjcRWfu3c"),
         (FIX + "og-page.html?" + tag, FIX + "og-page.html?" + tag, None), (FIX + "no-og.html?" + tag, "No image page", None), (FIX + "bad-og.html?" + tag, "Blocked image page", None)]
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    c = br.new_context(viewport={"width": 1000, "height": 1400})
    a = c.new_page(); a.on("pageerror", lambda e: errors.append(str(e))); a.on("dialog", lambda d: d.accept())
    a.goto(BASE); assert a.evaluate("CFG.SUPABASE_URL") == "http://127.0.0.1:54321", "not the local stack"
    a.click("#sbtn"); signup_email(a, f"SmokeLc{tag}"); expect(a.get_by_text("Pick your topics")).to_be_visible(timeout=T); a.click("text=Skip")
    ok = a.evaluate("async u=>(await sb.rpc('link_ok',{p_url:u})).data", FIX + "og-page.html"); assert ok, "fixture URL blocked by link filter"
    rows = a.evaluate("async L=>{for(const [u,t] of L){const{error}=await sb.from('library_items').insert({user_id:USER.id,url:u,title:t,kind:/youtu/.test(u)?'Video':'Podcast',category:'Science'});if(error)throw error}return L.length}", [[u, t] for u, t, _ in ITEMS])
    a.goto(BASE + "#profile"); a.reload(); a.click("[data-pt=Library]")
    expect(a.locator(".lc")).to_have_count(len(ITEMS), timeout=T); step(f"{len(ITEMS)} library items render as link cards")
    for u, t, vid in ITEMS[:4]:
        card = a.locator(".lc", has_text=t); expect(card.locator(f'.lth img[src="https://img.youtube.com/vi/{vid}/hqdefault.jpg"]')).to_have_count(1)
        expect(card.locator(".lsite")).to_contain_text("YouTube"); expect(card.locator(".play")).to_have_count(1)
        assert card.locator("a.lnk").get_attribute("href") == u and card.locator("a.lnk").get_attribute("target") == "_blank" and "noopener" in card.locator("a.lnk").get_attribute("rel")
    step("YouTube watch?v= / youtu.be / shorts / m.youtube -> hqdefault thumbnail, 'YouTube', play overlay, new-tab link")
    og = a.locator(".lc", has_text="Deep Sea Voices"); expect(og).to_have_count(1, timeout=T)
    expect(og.locator('.lth img[src="https://img.youtube.com/vi/aqz-KE-bpKQ/hqdefault.jpg"]')).to_have_count(1); expect(og.locator(".lsite")).to_contain_text("Ocean Pod")
    step("og:image + og:title + og:site_name fetched by the link-preview function (title shown when the item has none)")
    expect(a.locator(".lc", has_text="No image page").locator(".lfb")).to_be_visible(timeout=T); expect(a.locator(".lc", has_text="No image page").locator(".lfb")).to_contain_text("127.0.0.1")
    expect(a.locator(".lc", has_text="No image page").locator(".lfb svg.mk")).to_have_count(1); step("No image -> Sage fallback tile with Pod Club logo + domain")
    a.wait_for_function("async()=>{const r=(await sb.from('library_items').select('preview_at').eq('user_id',USER.id)).data;return r.every(x=>x.preview_at)}", timeout=T)
    expect(a.locator(".lc", has_text="Blocked image page").locator(".lfb")).to_be_visible(); step("Adult image host -> no thumbnail (fallback tile)")
    db = a.evaluate("async()=>(await sb.from('library_items').select('url,thumb_url,preview_title,preview_site,preview_at').eq('user_id',USER.id)).data")
    by = {r["url"]: r for r in db}
    assert by[ITEMS[0][0]]["thumb_url"].endswith("aqz-KE-bpKQ/hqdefault.jpg") and by[ITEMS[4][0]]["preview_title"] == "Deep Sea Voices & Whale Songs" and by[ITEMS[4][0]]["preview_site"] == "Ocean Pod", by
    assert by[ITEMS[5][0]]["thumb_url"] is None and by[ITEMS[5][0]]["preview_at"] and by[ITEMS[6][0]]["thumb_url"] is None, by
    step("Previews cached on the rows (thumb_url/preview_title/preview_site/preview_at), misses marked so they aren't refetched")
    calls = []; a.on("request", lambda r: calls.append(r.url) if "/functions/v1/link-preview" in r.url else None)
    a.reload(); a.click("[data-pt=Library]"); expect(a.locator(".lc")).to_have_count(len(ITEMS), timeout=T); a.wait_for_timeout(1500)
    assert not calls, calls; expect(a.locator(".lc", has_text="Deep Sea Voices").locator(".lth img")).to_have_count(1); step("Reload: served from the cache, no refetch")
    a.screenshot(path=f"{SHOTS}/lc-1-library.png", full_page=True)
    card = a.locator(".lc", has_text="Big Buck Bunny"); card.hover(); bg = card.locator("a.lnk").evaluate("e=>getComputedStyle(e).backgroundColor"); assert bg != "rgba(0, 0, 0, 0)", bg; step("Hover state")
    with c.expect_page() as pi: card.locator(".lth").click()
    np = pi.value; assert np.url.startswith("https://www.youtube.com/watch?v=aqz-KE-bpKQ") or "youtube" in np.url or np.url == "about:blank", np.url; np.close()
    step("Clicking the card opens the link in a new tab")
    card.locator(".lmeta").click(); expect(a.get_by_text("Remove from Library")).to_be_visible(timeout=T); expect(a.locator(".lc")).to_have_count(1)
    step("'Details' opens the item page, which also shows the link card")
    m = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 390, "height": 844}}); mp = m.new_page(); mp.on("pageerror", lambda e: errors.append(str(e)))
    # same session in the mobile context
    st = c.storage_state(); m.close(); m = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 390, "height": 844}}, storage_state=st); mp = m.new_page(); mp.on("pageerror", lambda e: errors.append(str(e)))
    mp.goto(BASE + "#profile"); mp.click("[data-pt=Library]"); expect(mp.locator(".lc")).to_have_count(len(ITEMS), timeout=T)
    w = mp.locator(".lc").first.evaluate("e=>e.getBoundingClientRect().width"); assert 320 < w <= 390, w
    assert mp.evaluate("document.documentElement.scrollWidth") <= 390; mp.screenshot(path=f"{SHOTS}/lc-2-mobile.png", full_page=True); step(f"Mobile 390px: cards fit ({w:.0f}px), no horizontal scroll")
    assert not errors, errors; step("No JS errors"); br.close()
print(f"E2E link cards: {n} checks passed")
