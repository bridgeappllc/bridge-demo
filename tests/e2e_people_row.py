"""E2E: People page 'Everyone on Pod Club' row: newest first, excludes you / Smoke* / blocked, tap opens profile,
snap scrolling, lazy-loads past 30, no overflow at 375px. Local runs use 'Row*' names (+ 45 seeded people for paging);
hosted runs (BASE set) use only Smoke* users and check that none of them show up."""
import os, re, time, uuid
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); LOCAL = "127.0.0.1" in BASE
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 30000; n = 0; tag = str(int(time.time()) % 100000); P = "Row" if LOCAL else "Smoke"
V, Y, Z = f"{P}Vi{tag}", f"{P}Yu{tag}", f"{P}Zoe{tag}"
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
seeded = []
if LOCAL:
    import psycopg; db = psycopg.connect("postgresql://postgres@127.0.0.1:54322/postgres", autocommit=True)
    for i in range(45):
        u = str(uuid.uuid4()); seeded.append(u)
        db.execute("insert into auth.users (id, instance_id, aud, role, is_anonymous, created_at, updated_at) values (%s,'00000000-0000-0000-0000-000000000000','authenticated','authenticated',true,now(),now())", (u,))
        db.execute("insert into public.profiles (id, display_name, created_at) values (%s, %s, now() - interval '1 day' - %s * interval '1 minute')", (u, f"Seed{tag}{i:02d}", i))
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    def phone(who):
        ctx = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}}); pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); pg.on("dialog", lambda d: d.accept()); return pg
    def signup(pg, name):
        pg.goto(BASE); pg.click("#sbtn"); pg.fill("#nm", name); pg.click("#nok")
        [pg.click(f".topic[data-t={t}]") for t in ("Politics", "Science", "Culture")]; pg.click("#tgo"); expect(pg.locator("#ubtn")).to_be_visible(timeout=T)
    y, z, v = phone("Y"), phone("Z"), phone("V"); signup(y, Y); signup(z, Z); signup(v, V); zid = z.evaluate("ME"); yid = y.evaluate("ME")
    v.goto(BASE + "#people"); row = v.locator("#prow"); expect(row.locator(".pcard").first).to_be_visible(timeout=T)
    expect(v.locator("#prowh")).to_have_text("Everyone on Pod Club"); v.wait_for_timeout(500); v.screenshot(path=f"{SHOTS}/prow-1.png")
    names = row.locator(".pcard .pn").all_inner_texts()
    assert V not in names, names; step("Row shows people, never yourself")
    if LOCAL:
        assert names[:2] == [Z, Y], names[:3]; step("Newest first (Zoe, then Yu)")
    else:
        assert not [x for x in names if x.lower().startswith("smoke")], names; step("No Smoke* test users in the row")
    snap = row.evaluate("e=>[getComputedStyle(e).scrollSnapType,getComputedStyle(e).overflowX,getComputedStyle(e.querySelector('.pcard')).scrollSnapAlign]")
    assert snap[0].startswith("x mandatory") and snap[1] == "auto" and snap[2] == "start", snap; step("Horizontal scroll with snap")
    if LOCAL:
        c0 = row.locator(".pcard").count(); assert c0 >= 30, c0
        for _ in range(6): row.evaluate("e=>{e.scrollLeft=e.scrollWidth}"); v.wait_for_timeout(500)
        c = row.locator(".pcard").count(); assert c > c0 or c > 60, (c0, c); x = row.evaluate("e=>e.scrollLeft"); assert x > 1000, x
        v.screenshot(path=f"{SHOTS}/prow-2.png"); step(f"Lazy-loads more when scrolled to the end ({c} cards, scroll position kept)")
        row.evaluate("e=>{e.scrollLeft=0}")
        v.goto(BASE + f"#u/{yid}"); v.click("[data-fa=block]"); expect(v.locator(".toast")).to_be_visible(timeout=T)
        v.goto(BASE + "#people"); expect(row.locator(".pcard").first).to_be_visible(timeout=T); expect(row.locator(f"[data-pc='{yid}']")).to_have_count(0, timeout=T); step("Blocked people drop out of the row")
        row.locator(f"[data-pc='{zid}']").click()
    else:
        row.locator(".pcard").first.click()
    expect(v).to_have_url(re.compile("#u/"), timeout=T); expect(v.locator("h1")).to_be_visible(timeout=T); step("Tapping a card opens their profile")
    v.goto(BASE + "#people"); expect(row.locator(".pcard").first).to_be_visible(timeout=T)
    w = v.evaluate("document.documentElement.scrollWidth"); assert w <= 375, w; step("No page overflow at 375px")
    assert not errors, errors; step("No uncaught JS errors"); br.close()
if LOCAL:
    for u in seeded: db.execute("delete from auth.users where id=%s", (u,))
print(f"E2E people row: {n} checks passed")
