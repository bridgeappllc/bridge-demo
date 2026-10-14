"""E2E: 'Remind' (in-app for anyone who hasn't answered, email when they can get it) for 2-person and group pods.
Local: real flow through the local Edge Function + a mock Resend (no real email), email confirmed via the local DB.
LOCAL ONLY now that sign-up needs an emailed code (hosted checks live in smoke_hosted_remind.py).
Old hosted mode (BASE set): DRY RUN only (window.REMIND_DRY) — nothing is sent; the target's email is confirmed out-of-band:
the test writes user ids to $HANDOFF.ids and waits for $HANDOFF.ok (the operator confirms them via SQL with
@example.invalid addresses). Users are Smoke* so they get cleaned up."""
from authflow import signup_email, join_email, code_for, mails
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
    assert LOCAL, "local only: sign-up sends a real code email"
    def signup(pg, name, email=None):
        pg.goto(BASE); pg.click("#sbtn"); signup_email(pg, name, email)
        [pg.click(f".topic[data-t={t}]") for t in ("Politics", "Science", "Culture")]; pg.click("#tgo"); expect(pg.locator("#ubtn")).to_be_visible(timeout=T)
    a, b, g = phone("A"), phone("B"), phone("G"); signup(a, A); signup(b, Bn, BMAIL); signup(g, Gn)
    aid, bid, gid = (x.evaluate("ME") for x in (a, b, g))
    if LOCAL:
        db.execute("update profiles set email_reminders=false where id=%s", (gid,))  # G can't get email -> in-app only
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
        rb.click(); expect(a.locator(".toast")).to_contain_text("Reminder sent", timeout=T); expect(a.locator(".remrow .rmd.done")).to_have_text("✓ Reminded"); shot(a, "2-reminded")
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
    # unused invite link -> Resend invite (copy/share), no Remind
    br0 = mk(a, f"Smoke unused {tag}"); a.goto(BASE + f"#bridge/{br0['id']}/0"); expect(a.locator("#reinv #rsi")).to_be_visible(timeout=T)
    expect(a.locator("#reinv")).to_contain_text("hasn't joined yet"); assert a.locator("[data-rmd]").count() == 0
    a.evaluate("()=>{window.__shared=null;navigator.share=t=>{window.__shared=t.text;return Promise.resolve()}}"); a.click("#rsi")
    sh = a.evaluate("()=>window.__shared") or ""; assert br0["invite_token"] in sh, sh; step("Unused invite link: 'Resend invite' opens share/copy with the invite text")
    # no email (reminders off / legacy guest): in-app only
    br2 = mk(a, f"Smoke guest clip {tag}"); join(g, br2["invite_token"], Gn); a.goto(BASE + f"#bridge/{br2['id']}/0"); gb = a.locator(f".remrow [data-rmd='{gid}']"); expect(gb).to_be_visible(timeout=T)
    gb.click(); expect(a.locator(".toast")).to_contain_text("Reminder sent (in-app only)" if LOCAL else "Dry run ✓ in-app only", timeout=T); shot(a, "4-guest")
    if LOCAL:
        m = mock(); assert len(m) == 1, m; g.goto(BASE + "#notifications"); expect(g.locator(".nrow", has_text="reminded you to listen to")).to_contain_text(A, timeout=T)
    step("Someone who can't get email can still be reminded: in-app only, no email")
    b.goto(BASE + f"#bridge/{br1['id']}/1"); expect(b.locator(".steps")).to_be_visible(timeout=T); assert b.locator("#remnote").count() == 0; step("Signed-in (email) users never see the guest email prompt")
    # pending direct send (B has email)
    dbid = a.evaluate("async u=>{const{data,error}=await sb.rpc('send_direct_bridge',{p_to:u,p_clip_title:'Smoke direct remind',p_clip_url:'https://example.org/sdr',p_clip_type:'Podcast'});if(error)throw error;return data}", bid)
    a.goto(BASE + f"#bridge/{dbid}/0"); pb = a.locator(f"#rempend [data-rmd='{bid}']"); expect(pb).to_be_visible(timeout=T); assert a.locator("#rsi").count() == 0; shot(a, "6-pending")
    pb.click()
    if LOCAL:
        expect(a.locator("#rempend .rmd.done")).to_have_text("✓ Reminded", timeout=T); expect(a.locator(".toast")).to_have_text("Reminder sent"); m = mock(); assert len(m) == 2 and "Smoke direct remind" in m[1]["html"], len(m)
        b.goto(BASE + "#notifications"); b.locator(".nrow", has_text="reminded you to listen to").filter(has_text="Smoke direct remind").click(); expect(b).to_have_url(re.compile("#bridges"), timeout=T)
    else: expect(a.locator(".toast")).to_contain_text("Dry run ✓ would email", timeout=T)
    step("Pending direct send: recipient can be reminded before accepting; notification opens their Pods inbox")
    # group pod
    pod = a.evaluate("async([b,g])=>{const{data,error}=await sb.rpc('create_group_pod',{p_name:'Smoke remind pod',p_members:[b,g]});if(error)throw error;return data}", [bid, gid])
    a.evaluate("async p=>{const{error}=await sb.rpc('share_to_group_pod',{p_pod:p,p_title:'Smoke group remind ep',p_url:'https://example.org/sgre',p_kind:'Podcast',p_note:''});if(error)throw error}", pod)
    a.goto(BASE + f"#pod/{pod}"); expect(a.locator("#gmembers summary")).to_contain_text("2 can be reminded", timeout=T); a.click("#gmembers summary")
    expect(a.locator(f"#gmembers [data-rmd='{bid}']")).to_be_visible(); expect(a.locator(f"#gmembers [data-rmd='{gid}']")).to_be_visible(); shot(a, "3-group")
    a.locator(f"#gmembers [data-rmd='{bid}']").click()
    if LOCAL:
        expect(a.locator(".toast")).to_contain_text("Reminder sent", timeout=T); expect(a.locator("#gmembers .rmd.done")).to_have_text("✓ Reminded")
        m = mock(); assert len(m) == 3 and f"#pod/{pod}" in m[2]["html"] and "Smoke group remind ep" in m[2]["html"]; step("Group pod: remind a member from Members -> email with the latest clip + Reminded state")
        # opt-out
        b.goto(BASE + "#profile"); b.click("[data-pt=Settings]"); t = b.locator("#erem"); expect(t).to_be_checked(timeout=T); t.uncheck(); expect(b.locator(".toast")).to_contain_text("Reminder emails off", timeout=T)
        br3 = mk(a, f"Smoke optout {tag}"); join(b, br3["invite_token"], Bn); a.goto(BASE + f"#bridge/{br3['id']}/0"); expect(a.locator(".steps")).to_be_visible(timeout=T); a.wait_for_timeout(1500)
        ob = a.locator(f".remrow [data-rmd='{bid}']"); expect(ob).to_be_visible(timeout=T); ob.click(); expect(a.locator(".toast")).to_contain_text("Reminder sent (in-app only)", timeout=T)
        assert len(mock()) == 3; step("Settings 'Email me reminders' off is honored: in-app only, no email")
        b.reload(); b.click("[data-pt=Settings]"); expect(b.locator("#erem")).not_to_be_checked(timeout=T); b.locator("#erem").check(); expect(b.locator(".toast")).to_contain_text("Reminder emails on", timeout=T)
    else:
        expect(a.locator(".toast")).to_contain_text("Dry run ✓", timeout=T); step("Group pod: Remind button for the member with email, none for the guest (dry run)")
    st = a.evaluate("async()=>{const r=await fetch(CFG.SUPABASE_URL+'/functions/v1/remind',{method:'POST',headers:{apikey:CFG.SUPABASE_ANON_KEY,'Content-Type':'application/json'},body:'{}'});return r.status}")
    assert st == 401, st; step("Function rejects unauthenticated calls")
    assert not [x for x in bodies if BMAIL in x], "email leaked to client"; step("The target's email never appears in any response to the browser")
    w = a.evaluate("document.documentElement.scrollWidth"); assert w <= 375, w; step("No overflow at 375px")
    assert not errors, errors; step("No uncaught JS errors"); br.close()
print(f"E2E remind: {n} checks passed")
