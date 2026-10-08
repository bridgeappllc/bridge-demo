"""End-to-end: two people in two separate browser contexts (separate storage =
separate anonymous users) go through create -> invite link -> join -> answer ->
rate -> chat both ways, against the local Supabase-compatible stack
(real Postgres + real GoTrue auth + real PostgREST). Also checks persistence
after reload, the reveal rules, and that a 3rd person can't join."""
import re, sys, os
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/")
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 15000
results = []
def step(name): results.append(name); print("  ✓", name)

with sync_playwright() as p:
    br = p.chromium.launch()
    iphone = p.devices["iPhone 13"]
    paulc = br.new_context(**iphone); samc = br.new_context(**iphone); evec = br.new_context(**iphone)
    paulc.grant_permissions(["clipboard-read", "clipboard-write"])
    errors = []
    pages = []
    for c, who in ((paulc, "paul"), (samc, "sam"), (evec, "eve")):
        pg = c.new_page(); pg.on("dialog", lambda d: d.accept())
        pg.on("pageerror", lambda e, who=who: errors.append(f"{who}: {e}"))
        pages.append(pg)
    paul, sam, eve = pages
    shot = lambda pg, n: pg.screenshot(path=f"{SHOTS}/{n}.png", full_page=True)

    # --- Paul signs up and creates a bridge from a pasted link
    paul.goto(BASE); paul.click("#sbtn"); paul.fill("#nm", "Paul"); paul.click("#nok")
    expect(paul.get_by_text("Pick your topics")).to_be_visible(timeout=T)
    for t in ("Politics", "Economics", "Culture"): paul.click(f".topic[data-t={t}]")
    paul.click("#tgo"); expect(paul.get_by_text("No bridges yet")).to_be_visible(timeout=T); step("Paul signs up (anonymous auth + profile), picks topics")
    paul.click("text=🌉 Meet Me on the Bridge")
    paul.fill("#murl", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"); paul.fill("#mtitle", "A video we disagree about"); paul.fill("#mfriend", "Sam"); paul.fill("#mrew", "5")
    paul.click("#mgo"); expect(paul.locator("#itxt")).to_be_visible(timeout=T)
    invite = paul.locator("#itxt").input_value()
    m = re.search(r"(http://\S+#b/([0-9a-f]{32}))", invite); assert m, invite
    link, token = m.group(1), m.group(2)
    assert "A video we disagree about" in invite and "youtube.com" in invite and "$5" in invite
    shot(paul, "01-paul-invite"); step(f"Paul creates bridge; invite text includes unique link …#b/{token[:6]}…")
    paul.click("#cp"); assert paul.evaluate("navigator.clipboard.readText()") == invite; step("Copy invite text puts it on the clipboard")
    paul.click("#nx")
    expect(paul.get_by_text("Answer three questions")).to_be_visible(timeout=T)
    expect(paul.get_by_text("Sam hasn't joined yet.")).to_be_visible(timeout=T)

    # --- Sam opens the link on "his phone"
    sam.goto(link)
    expect(sam.get_by_text("Paul invited you to meet on the Bridge")).to_be_visible(timeout=T)
    expect(sam.get_by_text("A video we disagree about")).to_be_visible(); shot(sam, "02-sam-invite-landing")
    sam.fill("#jname", "Sam"); sam.click("#jgo")
    expect(sam.get_by_text("Answer three questions")).to_be_visible(timeout=T); step("Sam opens link, enters only his name, joins")
    expect(sam.get_by_text("Paul hasn't answered yet.")).to_be_visible(timeout=T)

    # --- Paul answers first; Sam should see the lock message, not the content
    for i, t in enumerate(["Paul moment", "Paul agreed/disagreed", "Paul takeaway"]): paul.locator(".q").nth(i).fill(t)
    paul.click("#qsave"); expect(paul.get_by_text("Rate it")).to_be_visible(timeout=T)
    paul.click("text=Answer"); expect(paul.get_by_text("Sam hasn't answered yet — you'll see their answers here when they do.")).to_be_visible(timeout=T)
    expect(sam.get_by_text("🔒 Paul has answered — submit yours to see theirs.")).to_be_visible(timeout=T)
    assert sam.get_by_text("Paul moment").count() == 0; step("Paul answers; Sam sees progress (live update) but not the content")
    # Sam types while a background refresh happens -> text must survive
    sam.locator(".q").nth(0).fill("Sam moment")
    sam.wait_for_timeout(5000)
    assert sam.locator(".q").nth(0).input_value() == "Sam moment"; step("Background refresh doesn't wipe what Sam is typing")
    sam.locator(".q").nth(1).fill("Sam agreed/disagreed"); sam.locator(".q").nth(2).fill("Sam takeaway")
    sam.click("#qsave"); expect(sam.get_by_text("Rate it")).to_be_visible(timeout=T)
    sam.click("text=Answer"); expect(sam.get_by_text("Paul moment")).to_be_visible(timeout=T)
    expect(paul.get_by_text("Sam moment")).to_be_visible(timeout=T); shot(paul, "03-paul-sees-both-answers")
    step("After both answer, each sees the other's answers")

    # --- Rate: Paul 2 (Propaganda), Sam 8 (Redpilled)
    paul.click("text=Rate"); paul.locator("#rs").fill("2"); expect(paul.locator("#rl")).to_have_text("Propaganda · 2"); paul.click("#rsave")
    expect(paul.get_by_text("💬 Talk")).to_be_visible(timeout=T)
    expect(paul.get_by_text("hasn't rated yet — they'll see the chat once they do")).to_be_visible()
    paul.fill("#ct", "Hey Sam, I thought it was pretty one-sided."); paul.click("#cs")
    expect(paul.locator(".bub.me")).to_have_text("Hey Sam, I thought it was pretty one-sided.", timeout=T)
    sam.click("text=Rate"); expect(sam.get_by_text("🔒 Paul has rated — submit yours to see theirs.")).to_be_visible(timeout=T)
    assert sam.locator("#chat").count() == 0; step("Paul rates and posts; Sam's chat stays locked until he rates")
    sam.locator("#rs").fill("8"); sam.click("#rsave")
    expect(sam.get_by_text("💬 Talk")).to_be_visible(timeout=T)
    expect(sam.locator(".bub").first).to_have_text("Hey Sam, I thought it was pretty one-sided.", timeout=T)
    expect(sam.get_by_text("Propaganda 2")).to_be_visible(); step("Sam rates; sees Paul's rating + Paul's message")
    sam.fill("#ct", "Interesting — I came away convinced. Where did it lose you?"); sam.click("#cs")
    expect(paul.locator(".bub:not(.me)")).to_have_text("Interesting — I came away convinced. Where did it lose you?", timeout=T)
    expect(paul.get_by_text("Redpilled 8")).to_be_visible(timeout=T)
    paul.fill("#ct", "The second half. Want to call?"); paul.press("#ct", "Enter")
    expect(sam.locator(".bub:not(.me)").last).to_have_text("The second half. Want to call?", timeout=T)
    shot(paul, "04-paul-chat"); shot(sam, "05-sam-chat"); step("Chat works both ways (stored, shows up for the other person)")
    sam.wait_for_timeout(1500)
    assert paul.get_by_text("Good point. I see it differently").count() == 0; step("No simulated replies")

    # --- Your Bridges shows progress for both; persists across reload
    paul.goto(BASE + "#bridges"); paul.reload()
    card = paul.locator(".card", has_text="You & Sam"); expect(card).to_be_visible(timeout=T)
    expect(card).to_contain_text("💬 Chat open"); expect(card).to_contain_text("Sam: ✓ answered · ✓ rated")
    shot(paul, "06-paul-bridges"); step("Your Bridges lists the real bridge with both people's progress after reload (session persisted)")
    sam.goto(BASE + "#bridges"); expect(sam.locator(".card", has_text="You & Paul")).to_contain_text("Invited by Paul", timeout=T)
    sam.goto(link); expect(sam.get_by_text("💬 Talk")).to_be_visible(timeout=T); step("Re-opening the invite link takes a member straight to the bridge")

    # --- A third person with the link is refused; outsider can't open by id
    eve.goto(link); expect(eve.get_by_text("This bridge is full")).to_be_visible(timeout=T); step("3rd person with the link is refused (bridge is full)")
    eve.goto(BASE + "#b/" + "0" * 32); expect(eve.get_by_text("Invite not found")).to_be_visible(timeout=T); step("Bogus invite token -> 'Invite not found'")
    bid = re.search(r"#bridge/([0-9a-f-]{36})", sam.url) or re.search(r"bridge/([0-9a-f-]{36})", paul.evaluate("document.body.innerHTML"))
    eve.goto(BASE); eve.click("#sbtn"); eve.fill("#nm", "Eve"); eve.click("#nok"); expect(eve.get_by_text("Pick your topics")).to_be_visible(timeout=T)
    eve.goto(BASE + "#bridge/" + bid.group(1)); expect(eve.get_by_text("Bridge not found")).to_be_visible(timeout=T); step("Signed-in outsider opening the bridge URL directly sees nothing")

    # --- Profile stats + rename
    paul.goto(BASE + "#profile"); expect(paul.locator(".stat")).to_contain_text("1Sent", timeout=T); expect(paul.locator(".stat")).to_contain_text("1Read")
    paul.click("[data-pt=Settings]"); paul.fill("#pname", "Paul G"); paul.click("#psave"); expect(paul.locator("header")).to_contain_text("Hi, Paul G", timeout=T)
    paul.reload(); expect(paul.locator("header")).to_contain_text("Hi, Paul G", timeout=T); step("Profile shows real Sent/Read counts; name change persists (profiles table)")

    # --- Unconfigured build shows setup notice instead of breaking
    raw = br.new_context().new_page(); raw.goto("file://" + os.path.join(os.path.dirname(SHOTS), "..", "index.html")); expect(raw.get_by_text("Almost ready")).to_be_visible(timeout=T); step("Unconfigured index.html shows an 'Almost ready' setup notice")

    # --- ?b=<token> alias
    p2 = br.new_context(**iphone).new_page(); p2.goto(BASE + "?b=" + token); expect(p2.get_by_text("This bridge is full")).to_be_visible(timeout=T); step("?b=<token> link form also works")
    assert not errors, errors; step("No uncaught JS errors in any page")
    br.close()
print(f"\nE2E: {len(results)} checks passed")
