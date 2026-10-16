"""Hosted-safe smoke for link cards (no email): 1 Smoke account via hosted_users adds public YouTube links (watch?v=,
youtu.be, shorts, m.youtube) + an Apple Podcasts episode; Library shows thumbnail cards (YouTube direct, Apple via the
hosted link-preview edge function), previews are cached on the rows, cards open in a new tab. Screenshots desktop + 390px."""
import os, time
from hosted_users import make, confirm
from playwright.sync_api import sync_playwright, expect
BASE = os.environ["BASE"]; T = 30000; n = 0; tag = str(int(time.time()) % 100000)
OUT = os.environ.get("OUT_DIR", "/workspace/podclub")
ITEMS = [("https://podcasts.apple.com/us/podcast/the-daily/id1200361736", "The Daily", "Podcast", "Politics"),
         ("https://m.youtube.com/watch?v=Unzc731iCUY", "How to speak so that people want to listen", "Video", "Culture"),
         ("https://youtube.com/shorts/Oos4ojutOMM", "Weightless: paragliding over Maui", "Video", "Science"),
         ("https://youtu.be/arj7oStGLkU?si=share", "Inside the mind of a master procrastinator", "Video", "Culture"),
         ("https://www.youtube.com/watch?v=iG9CE55wbtY&t=12s", "Do schools kill creativity?", "Video", "Education")]
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    c = br.new_context(viewport={"width": 1000, "height": 1500}); a = c.new_page(); a.on("pageerror", lambda e: errors.append(str(e)))
    a.on("response", lambda r: print("    link-preview:", r.status, r.text()[:160], flush=True) if "/functions/v1/link-preview" in r.url and r.request.method == "POST" else None)
    ia = make(a, BASE, f"SmokeCards{tag}"); confirm(BASE, [(a, ia)])
    for u, t, k, cat in ITEMS:
        e = a.evaluate("async([u,t,k,c])=>{const{error}=await sb.from('library_items').insert({user_id:USER.id,url:u,title:t,kind:k,category:c});return error}", [u, t, k, cat]); assert not e, e
    a.goto(BASE + "#profile"); a.reload(); a.click("[data-pt=Library]"); expect(a.locator(".lc")).to_have_count(len(ITEMS), timeout=T); step("5 library items render as link cards")
    for u, t, k, _ in ITEMS[1:]:
        card = a.locator(".lc", has_text=t); expect(card.locator(".lth img")).to_have_count(1); assert "img.youtube.com/vi/" in card.locator(".lth img").get_attribute("src")
        assert card.locator("a.lnk").get_attribute("href") == u and card.locator("a.lnk").get_attribute("target") == "_blank"
    step("YouTube variants -> hqdefault thumbnails, new-tab links")
    for _ in range(90):  # poll (wait_for_function doesn't await async predicates)
        if a.evaluate("async()=>(await sb.from('library_items').select('preview_at').eq('user_id',USER.id)).data.every(x=>x.preview_at)"): break
        a.wait_for_timeout(500)
    else: raise AssertionError("previews never cached")
    db = a.evaluate("async()=>(await sb.from('library_items').select('url,thumb_url,preview_site').eq('user_id',USER.id)).data"); ap = [r for r in db if "apple" in r["url"]][0]
    assert ap["thumb_url"] and ap["preview_site"] == "Apple Podcasts", ap; step("Previews cached on the rows (Apple Podcasts og:image via the link-preview edge function)")
    a.reload(); a.click("[data-pt=Library]"); expect(a.locator(".lc")).to_have_count(len(ITEMS), timeout=T)
    a.wait_for_function("[...document.querySelectorAll('.lth img')].every(i=>i.complete)", timeout=T); a.wait_for_timeout(1200)
    a.screenshot(path=f"{OUT}/library-cards.png", full_page=True); step(f"Screenshot {OUT}/library-cards.png")
    with c.expect_page() as pi: a.locator(".lc", has_text="Do schools kill creativity").locator(".lth").click()
    np = pi.value; np.wait_for_load_state("domcontentloaded", timeout=T); assert "youtube.com" in np.url, np.url; np.close(); step("Card opens YouTube in a new tab")
    m = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 390, "height": 844}}, storage_state=c.storage_state()); mp = m.new_page(); mp.on("pageerror", lambda e: errors.append(str(e)))
    mp.goto(BASE + "#profile"); mp.click("[data-pt=Library]"); expect(mp.locator(".lc")).to_have_count(len(ITEMS), timeout=T)
    mp.wait_for_function("[...document.querySelectorAll('.lth img')].every(i=>i.complete)", timeout=T); mp.wait_for_timeout(1200)
    cr = mp.evaluate("Math.max(...[...document.querySelectorAll('.lc')].map(e=>e.getBoundingClientRect().right))"); assert cr <= 390, cr; mp.screenshot(path=f"{OUT}/library-cards-mobile.png", full_page=True); step(f"Mobile 390px: cards fit; screenshot {OUT}/library-cards-mobile.png")
    assert not errors, errors; step("No JS errors"); br.close()
print(f"Smoke link cards: {n} checks passed")
