"""End-to-end smoke test: two people in two separate phone-sized browser contexts
(separate storage = separate anonymous users) go through create -> invite link ->
join -> answer -> rate -> chat both ways. Also checks persistence after reload,
reveal rules, a 3rd person being refused, and (REALTIME=1) that Supabase Realtime
delivers a chat message with polling effectively disabled.

  BASE=<url of the app>   (default http://127.0.0.1:8080/)
  P=, S=, E=              display names (default SmokePaul/SmokeSam/SmokeEve so
                          test rows can be found and deleted afterwards)
"""
import re, sys, os, tempfile, time
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/")
P, S, E = os.environ.get("P", "SmokePaul"), os.environ.get("S", "SmokeSam"), os.environ.get("E", "SmokeEve")
REALTIME = os.environ.get("REALTIME") == "1"
HERE = os.path.dirname(os.path.abspath(__file__)); SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(HERE, "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 20000
results = []
def step(name): results.append(name); print("  ✓", name, flush=True)

with sync_playwright() as p:
    br = p.chromium.launch()
    iphone = p.devices["iPhone 13"]
    paulc, samc, evec = br.new_context(**iphone), br.new_context(**iphone), br.new_context(**iphone)
    paulc.grant_permissions(["clipboard-read", "clipboard-write"])
    errors, pages = [], []
    for c, who in ((paulc, "paul"), (samc, "sam"), (evec, "eve")):
        pg = c.new_page(); pg.on("dialog", lambda d: d.accept())
        pg.on("pageerror", lambda e, who=who: errors.append(f"{who}: {e}"))
        pg.on("console", lambda m, who=who: print(f"    [{who} console.{m.type}] {m.text[:200]}", flush=True) if m.type in ("error",) and "realtime" not in m.text.lower() and "websocket" not in m.text.lower() else None)
        pages.append(pg)
    paul, sam, eve = pages
    def shot(pg, n):
        try: pg.screenshot(path=f"{SHOTS}/{n}.png", timeout=15000)
        except Exception as e: print(f"    (screenshot {n} skipped: {str(e).splitlines()[0][:80]})")

    # --- Paul signs up and creates a bridge from a pasted link
    paul.goto(BASE); paul.click("#sbtn"); paul.fill("#nm", P); paul.click("#nok")
    expect(paul.get_by_text("Pick your topics")).to_be_visible(timeout=T)
    for t in ("Politics", "Economics", "Culture"): paul.click(f".topic[data-t={t}]")
    paul.click("#tgo"); expect(paul.get_by_text("No bridges yet")).to_be_visible(timeout=T); step(f"{P} signs up (anonymous auth + profile), picks topics")
    paul.click("text=🌉 Meet Me on the Bridge")
    paul.fill("#murl", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"); paul.fill("#mtitle", "Smoke test video"); paul.fill("#mfriend", S); paul.fill("#mrew", "5")
    paul.click("#mgo"); expect(paul.locator("#itxt")).to_be_visible(timeout=T)
    invite = paul.locator("#itxt").input_value()
    m = re.search(r"(https?://\S+#b/([0-9a-f]{32}))", invite); assert m, invite
    link, token = m.group(1), m.group(2)
    assert link.startswith(BASE.rstrip("/")), (link, BASE)
    assert "Smoke test video" in invite and "youtube.com" in invite and "$5" in invite
    paul.locator("#itxt").scroll_into_view_if_needed(); paul.evaluate("window.scrollBy(0,120); const t=document.querySelector('#itxt'); t.scrollTop=t.scrollHeight"); shot(paul, "01-paul-invite"); step(f"Bridge created; invite text includes unique link {link[:60]}…")
    paul.click("#cp"); assert paul.evaluate("navigator.clipboard.readText()") == invite; step("Copy invite text puts it on the clipboard")
    paul.click("#nx")
    expect(paul.get_by_text("Answer three questions")).to_be_visible(timeout=T)
    expect(paul.get_by_text(f"{S} hasn't joined yet.")).to_be_visible(timeout=T)

    # --- Sam opens the link on "his phone"
    sam.goto(link)
    expect(sam.get_by_text(f"{P} invited you to meet on the Bridge")).to_be_visible(timeout=T)
    expect(sam.get_by_text("Smoke test video")).to_be_visible(); shot(sam, "02-sam-invite-landing")
    sam.fill("#jname", S); sam.click("#jgo")
    expect(sam.get_by_text("Answer three questions")).to_be_visible(timeout=T); step(f"{S} opens link, enters only a name, joins")
    expect(sam.get_by_text(f"{P} hasn't answered yet.")).to_be_visible(timeout=T)

    # --- Paul answers first; Sam sees the lock message, not the content
    for i, t in enumerate(["Paul moment", "Paul agreed/disagreed", "Paul takeaway"]): paul.locator(".q").nth(i).fill(t)
    paul.click("#qsave"); expect(paul.get_by_text("Rate it")).to_be_visible(timeout=T)
    paul.click("text=Answer"); expect(paul.get_by_text(f"{S} hasn't answered yet — you'll see their answers here when they do.")).to_be_visible(timeout=T)
    expect(sam.get_by_text(f"🔒 {P} has answered — submit yours to see theirs.")).to_be_visible(timeout=T)
    assert sam.get_by_text("Paul moment").count() == 0; step(f"{P} answers; {S} sees progress (live) but not the content")
    sam.locator(".q").nth(0).fill("Sam moment"); sam.wait_for_timeout(5000)
    assert sam.locator(".q").nth(0).input_value() == "Sam moment"; step("Background refresh doesn't wipe typing")
    sam.locator(".q").nth(1).fill("Sam agreed/disagreed"); sam.locator(".q").nth(2).fill("Sam takeaway")
    sam.click("#qsave"); expect(sam.get_by_text("Rate it")).to_be_visible(timeout=T)
    sam.click("text=Answer"); expect(sam.get_by_text("Paul moment")).to_be_visible(timeout=T)
    expect(paul.get_by_text("Sam moment")).to_be_visible(timeout=T); shot(paul, "03-paul-sees-both-answers")
    step("After both answer, each sees the other's answers")

    # --- Rate
    paul.click("text=Rate"); paul.locator("#rs").fill("2"); expect(paul.locator("#rl")).to_have_text("Propaganda · 2"); paul.click("#rsave")
    expect(paul.get_by_text("💬 Talk")).to_be_visible(timeout=T)
    paul.fill("#ct", "Hey, I thought it was pretty one-sided."); paul.click("#cs")
    expect(paul.locator(".bub.me")).to_have_text("Hey, I thought it was pretty one-sided.", timeout=T)
    sam.click("text=Rate"); expect(sam.get_by_text(f"🔒 {P} has rated — submit yours to see theirs.")).to_be_visible(timeout=T)
    assert sam.locator("#chat").count() == 0; step(f"{P} rates and posts; {S}'s chat stays locked until he rates")
    sam.locator("#rs").fill("8"); sam.click("#rsave")
    expect(sam.get_by_text("💬 Talk")).to_be_visible(timeout=T)
    expect(sam.locator(".bub").first).to_have_text("Hey, I thought it was pretty one-sided.", timeout=T)
    expect(sam.get_by_text("Propaganda 2")).to_be_visible(); step(f"{S} rates; sees {P}'s rating + message")
    sam.fill("#ct", "Interesting — I came away convinced. Where did it lose you?"); sam.click("#cs")
    expect(paul.locator(".bub:not(.me)")).to_have_text("Interesting — I came away convinced. Where did it lose you?", timeout=T)
    expect(paul.get_by_text("Redpilled 8")).to_be_visible(timeout=T)
    paul.fill("#ct", "The second half. Want to call?"); paul.press("#ct", "Enter")
    expect(sam.locator(".bub:not(.me)").last).to_have_text("The second half. Want to call?", timeout=T)
    [pg.evaluate("window.scrollTo(0,document.body.scrollHeight)") for pg in (paul, sam)]; shot(paul, "04-paul-chat"); shot(sam, "05-sam-chat"); step("Chat works both ways (stored, shows up for the other person)")
    bridge_path = re.search(r"#bridge/([0-9a-f-]{36})", paul.url).group(1)

    if REALTIME:  # reload both with polling ~disabled (10 min) so only Realtime can deliver
        for pg in (paul, sam): pg.goto(BASE + "?poll=600000#bridge/" + bridge_path + "/3")
        for pg in (paul, sam): pg.wait_for_function("window.__bridgeRealtime==='SUBSCRIBED' && window.__bridgeRealtimePg==='ok'", timeout=T)
        t0 = time.time(); sam.fill("#ct", "realtime ping"); sam.click("#cs")
        expect(paul.locator(".bub:not(.me)").last).to_have_text("realtime ping", timeout=10000)
        dt = time.time() - t0
        t0 = time.time(); paul.fill("#ct", "realtime pong"); paul.click("#cs")
        expect(sam.locator(".bub:not(.me)").last).to_have_text("realtime pong", timeout=10000)
        step(f"Realtime delivers chat both ways with polling disabled ({dt:.1f}s / {time.time()-t0:.1f}s)")
        # navigate between steps inside the bridge (re-creates the channel), then check again
        paul.click(".steps button:has-text('Rate')"); expect(paul.get_by_text("Ratings")).to_be_visible(timeout=T)
        paul.click(".steps button:has-text('Talk')"); expect(paul.get_by_text("💬 Talk")).to_be_visible(timeout=T)
        paul.wait_for_function("window.__bridgeRealtime==='SUBSCRIBED' && window.__bridgeRealtimePg==='ok'", timeout=T)
        sam.fill("#ct", "still live after navigating?"); sam.click("#cs")
        expect(paul.locator(".bub:not(.me)").last).to_have_text("still live after navigating?", timeout=10000)
        step("Realtime still works after in-bridge step navigation (polling disabled)")
    assert paul.get_by_text("Good point. I see it differently").count() == 0; step("No simulated replies")

    # --- Your Bridges shows progress for both; persists across reload
    paul.goto(BASE + "#bridges"); paul.reload()
    card = paul.locator(".card", has_text=f"You & {S}"); expect(card).to_be_visible(timeout=T)
    expect(card).to_contain_text("💬 Chat open"); expect(card).to_contain_text(f"{S}: ✓ answered · ✓ rated")
    shot(paul, "06-paul-bridges"); step("Your Bridges lists the bridge with both people's progress after reload (session persisted)")
    sam.goto(BASE + "#bridges"); expect(sam.locator(".card", has_text=f"You & {P}")).to_contain_text(f"Invited by {P}", timeout=T)
    sam.goto(link); expect(sam.get_by_text("💬 Talk")).to_be_visible(timeout=T); step("Re-opening the invite link takes a member straight to the bridge")

    # --- Outsiders
    eve.goto(link); expect(eve.get_by_text("This bridge is full")).to_be_visible(timeout=T); step("3rd person with the link is refused (bridge is full)")
    eve.goto(BASE + "#b/" + "0" * 32); expect(eve.get_by_text("Invite not found")).to_be_visible(timeout=T); step("Bogus invite token -> 'Invite not found'")
    eve.goto(BASE); eve.click("#sbtn"); eve.fill("#nm", E); eve.click("#nok"); expect(eve.get_by_text("Pick your topics")).to_be_visible(timeout=T)
    eve.goto(BASE + "#bridge/" + bridge_path); expect(eve.get_by_text("Bridge not found")).to_be_visible(timeout=T); step("Signed-in outsider opening the bridge URL directly sees nothing")

    # --- Profile stats + rename
    paul.goto(BASE + "#profile"); expect(paul.locator(".stat")).to_contain_text("1Sent", timeout=T); expect(paul.locator(".stat")).to_contain_text("1Read")
    paul.click("[data-pt=Settings]"); paul.fill("#pname", P + "G"); paul.click("#psave"); expect(paul.locator("header")).to_contain_text(f"Hi, {P}G", timeout=T)
    paul.reload(); expect(paul.locator("header")).to_contain_text(f"Hi, {P}G", timeout=T); step("Profile shows real Sent/Read counts; name change persists")

    # --- Unconfigured build shows setup notice instead of breaking
    html = open(os.path.join(HERE, "..", "index.html"), encoding="utf8").read()
    html = re.sub(r'SUPABASE_URL: "[^"]*"', 'SUPABASE_URL: ""', html, count=1)
    tmp = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False); tmp.write(html); tmp.close()
    raw = br.new_context().new_page(); raw.goto("file://" + tmp.name); expect(raw.get_by_text("Almost ready")).to_be_visible(timeout=T); step("Unconfigured build shows an 'Almost ready' notice")

    p2 = br.new_context(**iphone).new_page(); p2.goto(BASE + "?b=" + token); expect(p2.get_by_text("This bridge is full")).to_be_visible(timeout=T); step("?b=<token> link form also works")
    assert not errors, errors; step("No uncaught JS errors in any page")
    br.close()
print(f"\nE2E: {len(results)} checks passed")
