"""E2E for social features (3 phones): public profiles + @username (suggested),
People search, friend requests (send / accept / decline / cancel / unfriend),
pending badge, friends' libraries, Discover feed from friends, starting a bridge
directly with a friend from their library, library privacy (Everyone / Friends only /
Only me), shareable profile link (incl. before sign-up), block/unblock, old #lib route.
  BASE=<app url> (default http://127.0.0.1:8080/)   SHOTS_DIR=<dir>"""
import os, re, time
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/")
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 20000; n = 0; tag = str(int(time.time()) % 100000)
A, B, C = f"SmokeAlice{tag}", f"SmokeBob{tag}", f"SmokeCarol{tag}"
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
with sync_playwright() as p:
    br = p.chromium.launch(); iphone = p.devices["iPhone 13"]; errors, bad_http = [], []
    def phone(who):
        c = br.new_context(**iphone); c.grant_permissions(["clipboard-read", "clipboard-write"])
        c.add_init_script("window.__shared=[];navigator.share=d=>{window.__shared.push(d);return Promise.resolve()}")
        pg = c.new_page(); pg.on("dialog", lambda d: d.accept()); pg.on("pageerror", lambda e: errors.append(f"{who}: {e}"))
        pg.on("response", lambda r: bad_http.append(f"{who}: {r.status} {r.url[:120]}") if r.status >= 400 and "/rest/" in r.url else None); return pg
    def shot(pg, name, wait=2700, top=True):
        pg.wait_for_timeout(wait)
        if top: pg.evaluate("window.scrollTo(0,0)"); pg.wait_for_timeout(150)
        try: pg.screenshot(path=f"{SHOTS}/{name}.png", timeout=15000)
        except Exception: print("    (screenshot skipped)", name)
    def signup(pg, name, url=BASE):
        pg.goto(url); pg.click("#sbtn"); pg.fill("#nm", name); pg.click("#nok"); expect(pg.get_by_text("Pick your topics")).to_be_visible(timeout=T); pg.click("text=Skip")
    def item(pg, url, title, cat):
        pg.goto(BASE + "#profile"); pg.click("[data-pt=Add]"); pg.fill("#aurl", url); pg.fill("#atitle", title); pg.select_option("#acat", cat); pg.click("#asave"); expect(pg.get_by_text("Remove from Library")).to_be_visible(timeout=T)
    def profile_tab(pg, t): pg.goto(BASE + "#profile"); pg.click(f"[data-pt={t}]")
    def vis(pg, v): profile_tab(pg, "Settings"); pg.check(f"input[name=vis][value={v}]"); expect(pg.locator(".toast")).to_contain_text("Library visible to", timeout=T)

    alice, bob, carol = phone("alice"), phone("bob"), phone("carol")
    # --- Alice signs up, fills her library, claims the suggested @username
    signup(alice, A); expect(alice.get_by_text("No bridges yet")).to_be_visible(timeout=T)
    expect(alice.locator("nav")).to_contain_text("People")
    item(alice, f"https://example.org/fav-science-{tag}", "Cities and the climate", "Science")
    item(alice, f"https://example.org/fav-culture-{tag}", "Why we tell stories", "Culture")
    profile_tab(alice, "Settings"); expect(alice.locator("#puser")).to_have_value(re.compile(r"^smokealice\d+$"), timeout=T)
    expect(alice.locator("#uhint")).to_contain_text("Suggested"); handle = alice.locator("#puser").input_value()
    alice.fill("#pbio", "Science podcasts and long walks"); alice.locator("#puser").scroll_into_view_if_needed(); shot(alice, "s01-settings-username-privacy", top=False); alice.click("#pubsave")
    expect(alice.locator(".handle").first).to_have_text("@" + handle, timeout=T); expect(alice.locator("input[name=vis][value=friends]")).to_be_checked()
    step(f"@username auto-suggested from the name (@{handle}) and claimed with a bio; library defaults to 'Friends only'")
    bob_h = "smokebob" + tag
    signup(bob, B); profile_tab(bob, "Settings"); bob.fill("#puser", handle); expect(bob.locator("#uhint")).to_contain_text("is taken", timeout=T)
    bob.fill("#puser", "BAD name!"); expect(bob.locator("#puser")).to_have_value("badname")
    bob.fill("#puser", bob_h); expect(bob.locator("#uhint")).to_contain_text("available", timeout=T); bob.click("#pubsave"); expect(bob.locator(".handle").first).to_have_text("@" + bob_h, timeout=T)
    step("Username availability check: taken name flagged, invalid characters stripped, free name saved")

    # --- Bob finds Alice by name and by @username; her library is locked; sends a request
    bob.goto(BASE + "#people"); bob.fill("#pq", "smokeali"); row = bob.locator("#pres .person", has_text=A); expect(row).to_be_visible(timeout=T)
    expect(row).to_contain_text("@" + handle); expect(row).to_contain_text("Science podcasts"); shot(bob, "s02-people-search")
    bob.fill("#pq", "@" + handle); expect(bob.locator("#pres .person", has_text=A)).to_be_visible(timeout=T)
    bob.fill("#pq", "smokebob"); expect(bob.locator("#pres")).not_to_contain_text(B, timeout=T)
    step("People search finds others by name and by @username (never yourself)")
    bob.goto(BASE + "#u/@" + handle); expect(bob.get_by_text(f"{A}'s library is for friends")).to_be_visible(timeout=T)
    expect(bob.locator(".stat")).to_contain_text("🔒"); assert bob.locator(".card", has_text="Cities and the climate").count() == 0; shot(bob, "s03-profile-locked")
    step("Public profile shows name, @username, bio and stats, but a Friends-only library stays locked for strangers")
    bob.click("#fbtns [data-fa=add]"); expect(bob.locator("#fbtns")).to_contain_text("Requested · Cancel", timeout=T)
    expect(bob.get_by_text(f"You'll see it when {A} accepts your request.")).to_be_visible(timeout=T); step("Bob sends a friend request -> 'Requested'")

    # --- Alice: pending badge, accepts
    alice.goto(BASE + "#bridges"); alice.reload(); expect(alice.locator("#nbadge")).to_have_text("1", timeout=T)
    profile_tab(alice, "Library"); expect(alice.locator("[data-pt=Friends] .badge")).to_have_text("1", timeout=T); step("Pending request shows a badge on People and on the Friends tab")
    alice.goto(BASE + "#people"); req = alice.locator(".person", has_text=B); expect(req).to_be_visible(timeout=T); shot(alice, "s04-people-requests")
    req.locator("[data-fa=accept]").click(); expect(alice.locator(".toast")).to_contain_text("You're now friends", timeout=T); expect(alice.locator("#nbadge")).to_have_count(0, timeout=T)
    profile_tab(alice, "Friends"); expect(alice.locator(".person", has_text=B)).to_contain_text("✓ Friends", timeout=T); shot(alice, "s05-friends-tab")
    step("Alice accepts; Bob appears in her friends list; badge clears")

    # --- Bob now sees Alice's whole library, Discover feed, starts a bridge directly with her from an item
    bob.goto(BASE + "#u/@" + handle); expect(bob.locator("#fbtns")).to_contain_text("✓ Friends", timeout=T)
    expect(bob.locator(".card", has_text="Cities and the climate")).to_be_visible(timeout=T); expect(bob.locator(".card", has_text="Why we tell stories")).to_be_visible()
    expect(bob.locator(".stat")).to_contain_text("2Library"); bob.click("[data-ut=Friends]"); expect(bob.locator(".person", has_text=B)).to_have_count(1, timeout=T); bob.click("[data-ut=Library]"); shot(bob, "s06-friend-profile")
    step("Friend sees the full library on the profile (and the friends list tab)")
    profile_tab(bob, "Discover"); d = bob.locator(".card", has_text="Cities and the climate"); expect(d).to_contain_text(f"{A}'s library", timeout=T)
    bob.click(".chip[data-cat=Culture]"); expect(bob.locator(".card", has_text="Cities and the climate")).to_have_count(0, timeout=T); expect(bob.locator(".card", has_text="Why we tell stories")).to_be_visible()
    bob.click(".chip[data-cat=All]"); assert bob.get_by_text("Example").count() == 0; shot(bob, "s07-discover-friends")
    step("Discover shows friends' real recent library items with category filter (no example feed)")
    bob.goto(BASE + "#u/@" + handle); bob.locator(".card", has_text="Cities and the climate").click()
    bob.click(f"text=🌉 Meet {A} on the Bridge with this"); expect(bob.locator("#mfriend")).to_have_value(A, timeout=T); expect(bob.locator("#direct")).to_be_visible()
    expect(bob.locator("#mclip")).to_have_value(re.compile(r"[0-9a-f-]{36}")); shot(bob, "s08-new-bridge-with-friend", 300)
    bob.click("#mgo"); expect(bob.locator("#addednote")).to_contain_text(f"{A} is on this bridge", timeout=T); shot(bob, "s09-friend-added")
    step("Start a bridge from a friend's library item: friend prefilled and added directly")
    alice.goto(BASE + "#bridges"); card = alice.locator(".card", has_text=f"Invited by {B}"); expect(card).to_be_visible(timeout=T)
    expect(card).to_contain_text("Cities and the climate"); card.click(); expect(alice.get_by_text("Answer three questions")).to_be_visible(timeout=T)
    step("Alice finds the new bridge in her Bridges list without any link, ready to answer")
    alice.goto(BASE + "#u/" + bob.evaluate("ME")); expect(alice.locator("#meetfr")).to_be_visible(timeout=T); alice.click("#meetfr")
    expect(alice.locator("#mfriend")).to_have_value(B, timeout=T); expect(alice.locator("#direct")).to_be_visible(); step("'Meet <friend> on the Bridge' on a friend's profile prefills the friend")

    # --- privacy levels
    vis(alice, "private"); bob.goto(BASE + "#u/@" + handle); expect(bob.get_by_text(f"{A} keeps their library private")).to_be_visible(timeout=T)
    assert bob.locator(".card", has_text="Cities and the climate").count() == 0; step("'Only me': even a friend (and bridge partner) can't see the library")
    vis(alice, "everyone")
    alice.goto(BASE + "#profile"); alice.click("#shme2"); link = alice.evaluate("window.__shared")[-1]["text"]; assert link.endswith("#u/@" + handle), link
    step(f"Share my profile gives a link: {link[-40:]}")
    carol.goto(BASE + "#u/@" + handle); expect(carol.get_by_text("Sign up free (just your name) to see this profile.")).to_be_visible(timeout=T); shot(carol, "s10-profile-link-signup", 300)
    signup(carol, C, BASE + "#u/@" + handle); expect(carol.locator("h1")).to_have_text(A, timeout=T)
    expect(carol.locator(".card", has_text="Cities and the climate")).to_be_visible(timeout=T); expect(carol.locator("#fbtns")).to_contain_text("Add friend"); shot(carol, "s11-everyone-library")
    step("Profile link works before sign-up (lands on the profile after); 'Everyone' lets a stranger see the library")
    vis(alice, "friends"); carol.reload(); expect(carol.get_by_text(f"{A}'s library is for friends")).to_be_visible(timeout=T)
    bob.goto(BASE + "#u/@" + handle); expect(bob.locator(".card", has_text="Cities and the climate")).to_be_visible(timeout=T)
    step("Back to 'Friends only': stranger locked out again, friend sees it")

    # --- cancel / decline / unfriend / suggestions
    carol.click("#fbtns [data-fa=add]"); expect(carol.locator("#fbtns")).to_contain_text("Requested", timeout=T)
    carol.click("#fbtns [data-fa=cancel]"); expect(carol.locator("#fbtns")).to_contain_text("Add friend", timeout=T); step("Cancel a sent request")
    carol.click("#fbtns [data-fa=add]"); expect(carol.locator("#fbtns")).to_contain_text("Requested", timeout=T)
    alice.goto(BASE + "#people"); alice.locator(".person", has_text=C).locator("[data-fa=decline]").click(); expect(alice.locator(".person", has_text=C)).to_have_count(0, timeout=T)
    carol.reload(); expect(carol.locator("#fbtns")).to_contain_text("Add friend", timeout=T); step("Decline a request (requester can ask again later)")
    bob.goto(BASE + "#u/@" + handle); bob.click("#fbtns [data-fa=unfriend]"); expect(bob.locator("#fbtns")).to_contain_text("Add friend", timeout=T)
    expect(bob.locator(".card", has_text="Cities and the climate")).to_be_visible(timeout=T)
    step("Unfriend works; as a bridge partner Bob still sees a 'Friends only' library (existing rule kept)")
    alice.goto(BASE + "#people"); expect(alice.locator(".person", has_text=B)).to_contain_text("Add friend", timeout=T); shot(alice, "s12-people-suggestions")
    step("'People you've bridged with' suggests Bob again after unfriending")
    bob.goto(BASE + "#lib/" + alice.evaluate("ME")); expect(bob.locator("h1")).to_have_text(A, timeout=T); assert "#u/" in bob.url; step("Old #lib/<id> links open the new profile page")

    # --- block / unblock
    alice.goto(BASE + "#u/" + carol.evaluate("ME")); alice.click("[data-fa=block]"); expect(alice.locator("h1")).to_have_text("People", timeout=T)
    carol.goto(BASE + "#people"); carol.fill("#pq", A); expect(carol.locator("#pres")).to_contain_text("No one found", timeout=T)
    carol.goto(BASE + "#u/@" + handle); expect(carol.get_by_text("Profile not found")).to_be_visible(timeout=T); step("Block hides you from the blocked person (search + profile)")
    profile_tab(alice, "Settings"); blk = alice.locator(".person", has_text=C); expect(blk).to_be_visible(timeout=T); blk.locator("[data-fa=unblock]").click()
    expect(alice.locator(".person", has_text=C)).to_have_count(0, timeout=T); carol.reload(); expect(carol.locator("h1")).to_have_text(A, timeout=T); step("Unblock from Settings restores it")

    profile_tab(alice, "Library"); shot(alice, "s00-own-profile")
    assert not errors, errors; step("No uncaught JS errors")
    assert not bad_http, bad_http; step("No failed API calls")
    br.close()
print(f"\nE2E social: {n} checks passed")
