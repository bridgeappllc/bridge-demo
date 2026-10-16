"""Hosted-safe smoke for compact link cards + pod previews (no email): 2 Smoke accounts via hosted_users. A adds public
links to the Library (compact cards), creates a duo pod (Apple Podcasts) and a group pod with B (YouTube clip). Pods page
shows compact previews cached on bridges / group_pod_clips; B (not a member of the duo pod) opens its invite and sees no
URL / thumbnail. Screenshots: Library desktop + 390px, Pods page 390px (after thumbnails finish loading)."""
import os, time
from hosted_users import make, confirm
from playwright.sync_api import sync_playwright, expect
BASE = os.environ["BASE"]; T = 30000; n = 0; tag = str(int(time.time()) % 100000)
OUT = os.environ.get("OUT_DIR", "/workspace/podclub")
AP = "https://podcasts.apple.com/us/podcast/the-daily/id1200361736"
ITEMS = [(AP, "The Daily", "Podcast", "Politics"),
         ("https://m.youtube.com/watch?v=Unzc731iCUY", "How to speak so that people want to listen", "Video", "Culture"),
         ("https://youtube.com/shorts/Oos4ojutOMM", "Weightless: paragliding over Maui", "Video", "Science"),
         ("https://youtu.be/arj7oStGLkU?si=share", "Inside the mind of a master procrastinator", "Video", "Culture"),
         ("https://www.youtube.com/watch?v=iG9CE55wbtY&t=12s", "Do schools kill creativity?", "Video", "Education")]
YT = "https://www.youtube.com/watch?v=iG9CE55wbtY"
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
def poll(pg, js, arg=None, what="condition"):
    for _ in range(90):
        if pg.evaluate(js, arg): return
        pg.wait_for_timeout(500)
    raise AssertionError(what)
LOADED = "()=>[...document.querySelectorAll('.lth img')].every(i=>i.complete&&i.naturalWidth>0)"
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    ca = br.new_context(viewport={"width": 1000, "height": 1300}); a = ca.new_page()
    cb = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 390, "height": 844}}); b = cb.new_page()
    for pg in (a, b): pg.on("pageerror", lambda e: errors.append(str(e))); pg.on("dialog", lambda d: d.accept())
    ia = make(a, BASE, f"SmokePodA{tag}"); ib = make(b, BASE, f"SmokePodB{tag}"); confirm(BASE, [(a, ia), (b, ib)])
    for u, t, k, cat in ITEMS:
        e = a.evaluate("async([u,t,k,c])=>{const{error}=await sb.from('library_items').insert({user_id:USER.id,url:u,title:t,kind:k,category:c});return error}", [u, t, k, cat]); assert not e, e
    a.goto(BASE + "#profile"); a.reload(); a.click("[data-pt=Library]"); expect(a.locator(".lc")).to_have_count(len(ITEMS), timeout=T)
    poll(a, "async()=>(await sb.from('library_items').select('preview_at').eq('user_id',USER.id)).data.every(x=>x.preview_at)", what="library previews never cached")
    a.reload(); a.click("[data-pt=Library]"); expect(a.locator(".lc .lth img")).to_have_count(len(ITEMS), timeout=T); poll(a, LOADED, what="thumbs not loaded"); a.wait_for_timeout(800)
    w = a.locator(".lc .lth").first.evaluate("e=>e.getBoundingClientRect().width"); assert 90 <= w <= 122, w
    a.screenshot(path=f"{OUT}/cards-small.png", full_page=True); step(f"Library desktop: compact cards ({w:.0f}px thumbs), {OUT}/cards-small.png")
    bt = a.evaluate("async u=>{const r=await sb.rpc('create_bridge',{p_display_name:PROFILE.display_name,p_clip_title:'The Daily',p_clip_url:u,p_clip_type:'Podcast',p_clip_cat:'Politics',p_clip_creator:'',p_friend_label:'Sam',p_reward:''});if(r.error)throw r.error;return Array.isArray(r.data)?r.data[0]:r.data}", AP)
    gid = a.evaluate("async id=>{const r=await sb.rpc('create_group_pod',{p_name:'Smoke clip club',p_members:[id]});if(r.error)throw r.error;return r.data}", ib)
    a.evaluate("async([g,u])=>{const r=await sb.rpc('share_to_group_pod',{p_pod:g,p_title:'Do schools kill creativity?',p_url:u,p_kind:'Video',p_note:''});if(r.error)throw r.error}", [gid, YT])
    m = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 390, "height": 844}}, storage_state=ca.storage_state()); mp = m.new_page(); mp.on("pageerror", lambda e: errors.append(str(e)))
    mp.goto(BASE + "#profile"); mp.click("[data-pt=Library]"); expect(mp.locator(".lc .lth img")).to_have_count(len(ITEMS), timeout=T); poll(mp, LOADED, what="thumbs not loaded"); mp.wait_for_timeout(800)
    assert mp.evaluate("document.documentElement.scrollWidth") <= 390; mp.screenshot(path=f"{OUT}/cards-small-mobile.png", full_page=True); step(f"Library 390px, {OUT}/cards-small-mobile.png")
    mp.goto(BASE + "#bridges"); mp.reload()
    expect(mp.locator(".gcard", has_text="Smoke clip club").locator(".lth img")).to_have_count(1, timeout=T)
    expect(mp.locator(".card", has_text="You & Sam").first.locator(".lc .lsite")).to_contain_text("Apple Podcasts", timeout=T)
    poll(mp, "async id=>(await sb.from('bridges').select('preview_at').eq('id',id).single()).data.preview_at", bt["id"], "duo preview not cached")
    poll(mp, "async g=>(await sb.from('group_pod_clips').select('preview_at').eq('pod_id',g)).data.every(x=>x.preview_at)", gid, "group preview not cached")
    row = mp.evaluate("async id=>(await sb.from('bridges').select('thumb_url,preview_site').eq('id',id).single()).data", bt["id"]); assert row["preview_site"] == "Apple Podcasts", row
    step(f"Pods page: duo (Apple og:image via link-preview: {bool(row['thumb_url'])}) + group (YouTube) previews, cached on the pod rows")
    mp.reload(); expect(mp.locator(".card", has_text="You & Sam").first.locator(".lc")).to_have_count(1, timeout=T); poll(mp, LOADED, what="thumbs not loaded"); mp.wait_for_timeout(800)
    assert mp.evaluate("document.documentElement.scrollWidth") <= 390; mp.screenshot(path=f"{OUT}/pods-previews.png", full_page=True); step(f"Pods 390px, {OUT}/pods-previews.png")
    b.goto(BASE + "#b/" + bt["invite_token"]); expect(b.locator("#lockl")).to_be_visible(timeout=T)
    assert b.locator(".lc").count() == 0 and AP not in b.content(); assert b.evaluate("async id=>(await sb.from('bridges').select('clip_url,thumb_url').eq('id',id)).data", bt["id"]) == []
    pv = b.evaluate("async t=>(await sb.rpc('preview_bridge_v2',{p_token:t})).data", bt["invite_token"]); assert pv and not pv[0].get("clip_url") and "thumb_url" not in pv[0], pv
    step("Non-member invite page: no URL, no thumbnail (RPC + table)")
    b.goto(BASE + "#pod/" + gid); expect(b.locator(".gclip .lc .lth img")).to_have_count(1, timeout=T); step("Group member sees the clip card in the pod view")
    assert not errors, errors; step("No JS errors"); br.close()
print(f"Smoke pod cards: {n} checks passed; Smoke IDs: {ia} {ib}")
