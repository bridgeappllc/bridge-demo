"""Upgrade test for the rating-step removal (migration 20261009090000).
Phase 1 (BEFORE, old UI with rating, DB at v2): Paul + Sam answer, Paul rates and
posts, Sam stops at the old Rate step. Phase 2: apply the v3 migration; row counts
must be unchanged. Phase 3 (AFTER, new UI): Sam's bridge is now in Talk, he sees
Paul's earlier message and can reply; Paul sees the reply.
Same origin for both phases (so the phones keep their sessions): run
`INDEX=/tmp/bridge_index_current.html SB_KEY=... python3 tests/serve.py 8090`; this
test copies OLD_INDEX (pre-v3 index.html) there first, then the current index.html."""
import os, re, shutil, subprocess, psycopg
from playwright.sync_api import sync_playwright, expect
OLD = os.environ.get("BASE", "http://127.0.0.1:8090/"); NEW = OLD + "?v=3"; CUR = "/tmp/bridge_index_current.html"
OLD_INDEX = os.environ.get("OLD_INDEX", "/tmp/index_v2_backup.html")
DSN = "postgresql://postgres@127.0.0.1:54322/postgres"; ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(ROOT, "tests", "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 20000; n = 0
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
def counts():
    with psycopg.connect(DSN) as c:
        return c.execute("select (select count(*) from auth.users),(select count(*) from bridges),(select count(*) from bridge_members),(select count(*) from answers),(select count(*) from ratings),(select count(*) from messages),(select count(*) from library_items)").fetchone()
with sync_playwright() as p:
    br = p.chromium.launch(); iphone = p.devices["iPhone 13"]; errors = []
    pc, sc = br.new_context(**iphone), br.new_context(**iphone)
    paul, sam = pc.new_page(), sc.new_page()
    for who, pg in (("paul", paul), ("sam", sam)): pg.on("dialog", lambda d: d.accept()); pg.on("pageerror", lambda e, w=who: errors.append(f"{w}: {e}"))
    # ---- BEFORE (old UI, rating step exists)
    shutil.copy(OLD_INDEX, CUR)
    paul.goto(OLD); paul.click("#sbtn"); paul.fill("#nm", "SmokePaul"); paul.click("#nok"); paul.click("text=Skip")
    paul.goto(OLD + "#new"); paul.fill("#murl", "https://example.org/upgrade-ep"); paul.fill("#mtitle", "Upgrade episode"); paul.fill("#mfriend", "SmokeSam"); paul.click("#mgo")
    expect(paul.locator("#itxt")).to_be_visible(timeout=T); link = re.search(r"(https?://\S+#b/[0-9a-f]{32})", paul.locator("#itxt").input_value()).group(1)
    sam.goto(link); sam.fill("#jname", "SmokeSam"); sam.click("#jgo"); expect(sam.get_by_text("Answer three questions")).to_be_visible(timeout=T)
    paul.goto(OLD + "#bridges")
    paul.locator(".card", has_text="You & SmokeSam").click(); expect(paul.get_by_text("Answer three questions")).to_be_visible(timeout=T); paul.wait_for_timeout(1500)
    for pg, who in ((paul, "Paul"), (sam, "Sam")):
        for i in range(3): pg.locator(".q").nth(i).fill(f"{who} answer {i+1}")
        pg.click("#qsave"); expect(pg.get_by_text("Rate it")).to_be_visible(timeout=T)
    paul.locator("#rs").fill("3"); paul.click("#rsave"); expect(paul.get_by_text("💬 Talk")).to_be_visible(timeout=T)
    paul.fill("#ct", "Posted before the update"); paul.click("#cs"); expect(paul.locator(".bub.me")).to_have_text("Posted before the update", timeout=T)
    expect(sam.get_by_text("Save rating · Unlock chat")).to_be_visible(); assert sam.locator("#chat").count() == 0
    bid = re.search(r"#bridge/([0-9a-f-]{36})", paul.url).group(1)
    step("BEFORE (old app): both answered, Paul rated + posted; Sam stuck at the Rate step with chat locked")
    # ---- apply the v3 migration
    before = counts()
    subprocess.run(["psql", "-h", "127.0.0.1", "-p", "54322", "-U", "postgres", "-q", "-v", "ON_ERROR_STOP=1", "-f", os.path.join(ROOT, "supabase/migrations/20261009090000_remove_rating_step.sql")], check=True)
    after = counts(); assert before == after, (before, after); step(f"Migration applied; row counts unchanged {after} (users, bridges, members, answers, ratings, messages, library)")
    # ---- AFTER (new UI)
    shutil.copy(os.path.join(ROOT, "index.html"), CUR)
    sam.goto(NEW + "#bridges"); card = sam.locator(".card", has_text="You & SmokePaul"); expect(card).to_contain_text("💬 Chat open", timeout=T)
    card.click(); expect(sam.get_by_text("💬 Talk")).to_be_visible(timeout=T)
    expect(sam.locator(".bub").first).to_have_text("Posted before the update", timeout=T)
    assert sam.locator(".steps button").all_inner_texts() == ["✓ Joined", "✓ Answer", "Talk"], sam.locator(".steps button").all_inner_texts()
    step("AFTER (new app): Sam's bridge is in Talk (chat open), he sees Paul's earlier message")
    sam.goto(NEW + "#bridge/" + bid + "/3"); expect(sam.get_by_text("💬 Talk")).to_be_visible(timeout=T); step("Old step URL (/3) still lands in Talk")
    sam.fill("#ct", "Replying after the update"); sam.click("#cs")
    paul.goto(NEW + "#bridge/" + bid); expect(paul.get_by_text("💬 Talk")).to_be_visible(timeout=T)
    expect(paul.locator(".bub:not(.me)").last).to_have_text("Replying after the update", timeout=T)
    paul.fill("#ct", "Got it"); paul.click("#cs"); expect(sam.locator(".bub:not(.me)").last).to_have_text("Got it", timeout=T)
    sam.evaluate("window.scrollTo(0,document.body.scrollHeight)"); sam.screenshot(path=f"{SHOTS}/v3-upgrade-sam-talk.png")
    step("Chat works both ways after the update")
    bad = re.compile(r"\brat(e|ed|ing|ings)\b|propaganda|redpill", re.I)
    for pg in (paul, sam):
        for h in ("/0", "/1", "/2"):
            pg.goto(NEW + "#bridge/" + bid + h); pg.wait_for_timeout(1000); t = pg.locator("body").inner_text(); assert not bad.search(t), (h, bad.search(t).group(0))
    step("No rating wording on any step of a bridge that had ratings")
    assert not errors, errors; step("No uncaught JS errors"); br.close()
print(f"\nUpgrade test: {n} checks passed")
