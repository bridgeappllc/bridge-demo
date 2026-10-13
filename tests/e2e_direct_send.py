"""E2E (two phones): A opens B's profile -> 'Send a clip' (pick from library + note) -> B's bell shows a red
unread count -> notifications list -> incoming bridge in Your Pods -> accept -> answer 3 questions -> talk;
A gets 'joined' / 'answered' / message notifications and opens the bridge from one. Works locally (polling) and
on a hosted build (BASE=..., Realtime). Users are named Smoke* so hosted runs can be cleaned up."""
import os, re, time
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/")
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 30000; n = 0; tag = str(int(time.time()) % 100000); A, Bn = f"SmokeAnn{tag}", f"SmokeBen{tag}"
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    def phone(who):
        ctx = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}})
        ctx.add_init_script(f"window.NTF_MS={os.environ.get('NTF_MS', '4000')}"); pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); pg.on("dialog", lambda d: d.accept()); return pg
    def shot(pg, name): pg.wait_for_timeout(400); pg.screenshot(path=f"{SHOTS}/ds-{name}.png")
    def signup(pg, name):
        pg.goto(BASE); pg.click("#sbtn"); pg.fill("#nm", name); pg.click("#nok")
        [pg.click(f".topic[data-t={t}]") for t in ("Politics", "Science", "Culture")]; pg.click("#tgo"); expect(pg.locator("#ubtn")).to_be_visible(timeout=T)
    a, b = phone("A"), phone("B"); signup(a, A); signup(b, Bn); bid = b.evaluate("ME")
    expect(a.locator("#bell .nb")).to_be_hidden(); expect(a.locator("#bell")).to_have_attribute("aria-label", "Notifications")
    a.goto(BASE + "#profile"); a.click("[data-pt=Add]"); a.fill("#aurl", f"https://example.org/direct-{tag}"); a.fill("#atitle", "A talk worth arguing about"); a.click("#asave")
    expect(a.get_by_text("Remove from Library")).to_be_visible(timeout=T)
    a.goto(BASE + f"#u/{bid}"); sb = a.locator("#sendb"); expect(sb).to_contain_text(f"Send a clip to {Bn}", timeout=T); shot(a, "1-profile")
    step("Not friends: B's profile still offers 'Send a clip'")
    sb.click(); expect(a.locator("#sdsheet [role=dialog]")).to_be_visible(); a.select_option("#sdpick", label="A talk worth arguing about")
    expect(a.locator("#sdnew")).to_be_hidden(); a.fill("#sdnote", "Curious what you make of this"); shot(a, "2-picker")
    a.click("#sdgo"); expect(a.locator(".toast")).to_contain_text(f"Clip sent to {Bn}", timeout=T); expect(a.locator("#sdsheet")).to_have_count(0)
    step("Picker: choose from my library + note -> sent")
    a.goto(BASE + "#bridges"); expect(a.get_by_text(f"Sent to {Bn} · waiting")).to_be_visible(timeout=T); step("A sees it as 'Sent to B · waiting'")
    nb = b.locator("#bell .nb"); expect(nb).to_have_text("1", timeout=T); expect(b.locator("#bell")).to_have_attribute("aria-label", "Notifications, 1 unread")
    assert nb.evaluate("e=>getComputedStyle(e).backgroundColor") == "rgb(180, 35, 24)"; shot(b, "3-bell")
    step("B's bell shows a red unread count (no reload)")
    b.click("#bell"); row = b.locator(".nrow").first; expect(row).to_contain_text(f"{A} wants you to listen to this", timeout=T); expect(row).to_have_class(re.compile("un")); shot(b, "4-list")
    row.click(); expect(b).to_have_url(re.compile("#bridges")); expect(nb).to_be_hidden(timeout=T)
    inc = b.locator(".card.inc"); expect(inc).to_contain_text("A talk worth arguing about", timeout=T); expect(inc).to_contain_text("Curious what you make of this"); shot(b, "5-incoming")
    step("Tap notification -> marked read, opens Your Pods with the incoming bridge + note")
    b.click("[data-acc]"); expect(b).to_have_url(re.compile("#bridge/"), timeout=T)
    for i, t in enumerate(["B moment", "B surprised", "B takeaway"]): b.locator(".q").nth(i).fill(t)
    b.click("#qsave"); expect(b.get_by_text("💬 Talk")).to_be_visible(timeout=T); step("B accepts -> normal Answer 3 questions -> Talk")
    expect(a.locator("#bell .nb")).to_have_text(re.compile(r"[12]"), timeout=T)
    a.click("#bell"); expect(a.locator(".nrow", has_text="joined your pod")).to_be_visible(timeout=T); expect(a.locator(".nrow", has_text="answered the 3 questions")).to_be_visible(timeout=T)
    step("A is notified: B joined + answered")
    a.locator(".nrow", has_text="answered").click(); expect(a).to_have_url(re.compile("#bridge/"))
    for i, t in enumerate(["A moment", "A surprised", "A takeaway"]): a.locator(".q").nth(i).fill(t)
    a.click("#qsave"); expect(a.get_by_text("💬 Talk")).to_be_visible(timeout=T)
    a.goto(BASE + "#notifications"); a.click("#nall"); expect(a.locator("#bell .nb")).to_be_hidden(timeout=T); a.goto(BASE + "#bridges")
    b.fill("#ct", "Hi from Ben"); b.click("#cs"); expect(b.locator(".bub").last).to_have_text("Hi from Ben", timeout=T)
    expect(a.locator("#bell .nb")).to_have_text("1", timeout=T); a.click("#bell"); m = a.locator(".nrow", has_text="sent a message"); expect(m).to_contain_text(Bn)
    m.click(); expect(a.locator(".bub", has_text="Hi from Ben")).to_be_visible(timeout=T); step("B chats -> A gets a message notification that opens the chat")
    expect(a.locator("#ubtn")).to_be_visible(); w = a.evaluate("document.documentElement.scrollWidth"); assert w <= 375, w; step("No horizontal overflow at 375px")
    assert not errors, errors; step("No uncaught JS errors")
    br.close()
print(f"E2E direct send: {n} checks passed")
