"""E2E: 'Remind' (email a pod member who hasn't answered) for 2-person and group pods.
Local: real flow through the local Edge Function + a mock Resend (no real email), email confirmed via the local DB.
Hosted (BASE set): DRY RUN only (window.REMIND_DRY) — nothing is sent; the target's email is confirmed out-of-band:
the test writes user ids to $HANDOFF.ids and waits for $HANDOFF.ok (the operator confirms them via SQL with
@example.invalid addresses). Users are Smoke* so they get cleaned up."""
import json, os, re, time, urllib.request
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); LOCAL = "127.0.0.1" in BASE; MOCK = "http://127.0.0.1:54330/emails"
HANDOFF = os.environ.get("HANDOFF", "/tmp/remind-handoff")
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 30000; n = 0; tag = str(int(time.time()) % 100000); A, Bn, Gn = f"SmokeAri{tag}", f"SmokeBea{tag}", f"SmokeGus{tag}"
BMAIL = f"smoke-bea-{tag}@" + ("test.local" if LOCAL else "example.invalid")
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
def mock():
    return json.load(urllib.request.urlopen(MOCK))
if LOCAL:
    import psycopg; db = psycopg.connect("postgresql://postgres@127.0.0.1:54322/postgres", autocommit=True)
    urllib.request.urlopen(urllib.request.Request(MOCK, method="DELETE"))
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []; bodies = []
    def phone(who, dry=False):
        ctx = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}})
        if dry or not LOCAL: ctx.add_init_script("window.REMIND_DRY=true")
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); pg.on("dialog", lambda d: d.accept())
        def grab(r):
            try:
                if "/rest/v1/" in r.url or "/functions/v1/" in r.url: bodies.append(r.text())
            except Exception: pass
        pg.on("response", grab); return pg
    def shot(pg, name): pg.wait_for_timeout(400); pg.screenshot(path=f"{SHOTS}/rm-{name}.png")
    def signup(pg, name):
        pg.goto(BASE); pg.click("#sbtn"); pg.fill("#nm", name); pg.click("#nok")
        [pg.click(f".topic[data-t={t}]") for t in ("Politics", "Science", "Culture")]; pg.click("#tgo"); expect(pg.locator("#ubtn")).to_be_visible(timeout=T)
    a, b, g = phone("A"), phone("B"), phone("G"); signup(a, A); signup(b, Bn); signup(g, Gn)
    aid, bid, gid = (x.evaluate("ME") for x in (a, b, g))
    if LOCAL:
        db.execute("update auth.users set email=%s, email_confirmed_at=now(), is_anonymous=false where id=%s", (BMAIL, bid))
    else:
        open(HANDOFF + ".ids", "w").write(json.dumps({"b": bid, "email": BMAIL}))
        for _ in range(600):
            if os.path.exists(HANDOFF + ".ok"): break
            time.sleep(1)
        else: raise AssertionError("operator never confirmed the test email")
    # 2-person pod (A invites, B and the guest each join their own)
    mk = lambda pg, title: pg.evaluate("async t=>{const{data,error}=await sb.rpc('create_bridge',{p_display_name:PROFILE.display_name,p_clip_title:t,p_clip_url:'https://example.org/'+encodeURIComponent(t),p_clip_type:'Podcast',p_clip_cat:'',p_clip_creator:'',p_friend_label:'',p_reward:''});if(error)throw error;return data[0]||data}", title)
    join = lambda pg, tok, nm: pg.evaluate("async([t,n])=>{const{error}=await sb.rpc('join_bridge',{p_token:t,p_display_name:n});if(error)throw error}", [tok, nm])
    br1 = mk(a, f"Smoke remind clip {tag}"); join(b, br1["invite_token"], Bn)
    a.goto(BASE + f"#bridge/{br1['id']}/0"); rb = a.locator(".remrow [data-rmd]"); expect(rb).to_be_visible(timeout=T); expect(a.locator(".remrow")).to_contain_text(f"{Bn} hasn't answered yet.")
    shot(a, "1-bridge"); step("2-person pod: 'Remind' shows while the friend hasn't answered")
    if LOCAL:
        rb.click(); expect(a.locator(".toast")).to_contain_text(f"Reminder sent to {Bn}", timeout=T); expect(a.locator(".remrow .rmd.done")).to_have_text("✓ Reminded"); shot(a, "2-reminded")
        m = mock(); assert len(m) == 1, m; m = m[0]
        assert m["to"] == [BMAIL] and m["from"] == "Pod Club <hello@meetonthebridge.org>" and m["subject"] == f"{A} wants you to listen to this", m
        assert f"Smoke remind clip {tag}" in m["html"] and f"#bridge/{br1['id']}/1" in m["html"] and "#settings" in m["html"] and "Email me reminders" in m["html"], m["html"][:300]
        assert m["headers"]["List-Unsubscribe"].endswith("#settings>")
        open(f"{SHOTS}/rm-email.html", "w").write(m["html"]); step("Email sent via Resend (mock): from Pod Club, 'Ari wants you to listen to this', clip title, pod link, opt-out link")
        a.reload(); expect(a.locator(".remrow .rmd.done")).to_have_text("✓ Reminded", timeout=T); assert a.locator(".remrow [data-rmd]").count() == 0; step("After reload: still shows Reminded, no second reminder within 24h")
        b.goto(BASE + "#notifications"); row = b.locator(".nrow", has_text="reminded you to listen to"); expect(row).to_contain_text(A, timeout=T); row.click()
        expect(b).to_have_url(re.compile(f"#bridge/{br1['id']}"), timeout=T); step("Target gets an in-app notification that opens the pod")
    else:
        rb.click(); expect(a.locator(".toast")).to_contain_text("Dry run ✓ would email s***@e***.invalid", timeout=T); expect(a.locator(".remrow [data-rmd]")).to_be_visible()
        step("Dry run on hosted: the function validates + renders, returns only a masked address, sends nothing")
    # guest never offered
    br2 = mk(a, f"Smoke guest clip {tag}"); join(g, br2["invite_token"], Gn); a.goto(BASE + f"#bridge/{br2['id']}/0"); expect(a.locator(".steps")).to_be_visible(timeout=T); a.wait_for_timeout(1500)
    assert a.locator("[data-rmd]").count() == 0; step("Guests (no confirmed email) can't be reminded")
    # group pod
    pod = a.evaluate("async([b,g])=>{const{data,error}=await sb.rpc('create_group_pod',{p_name:'Smoke remind pod',p_members:[b,g]});if(error)throw error;return data}", [bid, gid])
    a.evaluate("async p=>{const{error}=await sb.rpc('share_to_group_pod',{p_pod:p,p_title:'Smoke group remind ep',p_url:'https://example.org/sgre',p_kind:'Podcast',p_note:''});if(error)throw error}", pod)
    a.goto(BASE + f"#pod/{pod}"); expect(a.locator("#gmembers summary")).to_contain_text("1 can be reminded", timeout=T); a.click("#gmembers summary")
    expect(a.locator(f"#gmembers [data-rmd='{bid}']")).to_be_visible(); assert a.locator(f"#gmembers [data-rmd='{gid}']").count() == 0; shot(a, "3-group")
    a.locator(f"#gmembers [data-rmd='{bid}']").click()
    if LOCAL:
        expect(a.locator(".toast")).to_contain_text(f"Reminder sent to {Bn}", timeout=T); expect(a.locator("#gmembers .rmd.done")).to_have_text("✓ Reminded")
        m = mock(); assert len(m) == 2 and f"#pod/{pod}" in m[1]["html"] and "Smoke group remind ep" in m[1]["html"]; step("Group pod: remind a member from Members -> email with the latest clip + Reminded state")
        # opt-out
        b.goto(BASE + "#profile"); b.click("[data-pt=Settings]"); t = b.locator("#erem"); expect(t).to_be_checked(timeout=T); t.uncheck(); expect(b.locator(".toast")).to_contain_text("Reminder emails off", timeout=T)
        br3 = mk(a, f"Smoke optout {tag}"); join(b, br3["invite_token"], Bn); a.goto(BASE + f"#bridge/{br3['id']}/0"); expect(a.locator(".steps")).to_be_visible(timeout=T); a.wait_for_timeout(1500)
        assert a.locator("[data-rmd]").count() == 0; step("Settings 'Email me reminders' (default on) -> off is honored")
        b.reload(); b.click("[data-pt=Settings]"); expect(b.locator("#erem")).not_to_be_checked(timeout=T); b.locator("#erem").check(); expect(b.locator(".toast")).to_contain_text("Reminder emails on", timeout=T)
    else:
        expect(a.locator(".toast")).to_contain_text("Dry run ✓", timeout=T); step("Group pod: Remind button for the member with email, none for the guest (dry run)")
    st = a.evaluate("async()=>{const r=await fetch(CFG.SUPABASE_URL+'/functions/v1/remind',{method:'POST',headers:{apikey:CFG.SUPABASE_ANON_KEY,'Content-Type':'application/json'},body:'{}'});return r.status}")
    assert st == 401, st; step("Function rejects unauthenticated calls")
    assert not [x for x in bodies if BMAIL in x], "email leaked to client"; step("The target's email never appears in any response to the browser")
    w = a.evaluate("document.documentElement.scrollWidth"); assert w <= 375, w; step("No overflow at 375px")
    assert not errors, errors; step("No uncaught JS errors"); br.close()
print(f"E2E remind: {n} checks passed")
