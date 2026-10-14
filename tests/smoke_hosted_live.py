"""Hosted-safe smoke for the merged build (sends NO email): People row, direct send (+ Remind on the pending send),
group pod (+ Remind, rating average), Remind dry-run for a legacy guest (in-app only), Resend invite, keep-your-account
screen, sign-up/invite forms (not submitted). Users: 3 Smoke email accounts via hosted_users + 1 Smoke legacy guest.
All Remind clicks are DRY RUN (window.REMIND_DRY). Clean up Smoke* users afterwards."""
import os, re, time
from hosted_users import make, confirm
from playwright.sync_api import sync_playwright, expect
BASE = os.environ["BASE"]; SHOTS = os.environ.get("SHOTS_DIR", "/tmp/shots-live"); os.makedirs(SHOTS, exist_ok=True)
T = 30000; n = 0; tag = str(int(time.time()) % 100000)
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
RPC = "async([f,a])=>{const{data,error}=await sb.rpc(f,a);if(error)throw error;return data}"
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    def phone(who):
        c = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}}); c.add_init_script("window.REMIND_DRY=true")
        pg = c.new_page(); pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); pg.on("dialog", lambda d: d.accept()); return pg
    shot = lambda pg, nm: (pg.wait_for_timeout(500), pg.screenshot(path=f"{SHOTS}/{nm}.png"))
    rpc = lambda pg, f, a: pg.evaluate(RPC, [f, a])
    A, B, C, G = (f"Smoke{x}{tag}" for x in ("Ann", "Ben", "Cat", "Gus"))
    a, b, c, g = phone("A"), phone("B"), phone("C"), phone("G")
    ia, ib, ic, ig = make(a, BASE, A), make(b, BASE, B), make(c, BASE, C), make(g, BASE, G)
    confirm(BASE, [(a, ia), (b, ib), (c, ic)]); step("3 Smoke email accounts + 1 legacy guest (no sign-up form, no email)")
    # keep screen for the guest
    g.reload(); expect(g.get_by_text("Add your email to keep your account")).to_be_visible(timeout=T); assert g.get_by_text("Skip").count() == 0; shot(g, "l-keep")
    step("Legacy guest: required 'Add your email to keep your account'")
    # people row
    a.goto(BASE + "#people"); a.reload(); expect(a.locator("#prow .pcard.you")).to_be_visible(timeout=T)
    assert a.locator("#prow .pcard").first.evaluate("e=>e.classList.contains('you')"); assert a.locator(f"#prow [data-pc='{ib}']").count() == 0; shot(a, "l-people")
    step(f"People row: 'You' card first, {a.locator('#prow .pcard').count() - 1} real people, Smoke* test users hidden")
    # direct send -> pending -> Remind (dry, would email) -> B accepts
    d = rpc(a, "send_direct_bridge", {"p_to": ib, "p_clip_title": f"Smoke live direct {tag}", "p_clip_url": "https://example.org/sld", "p_clip_type": "Podcast"})
    a.goto(BASE + f"#bridge/{d}/0"); pb = a.locator(f"#rempend [data-rmd='{ib}']"); expect(pb).to_be_visible(timeout=T); pb.click()
    expect(a.locator(".toast")).to_contain_text("Dry run ✓ would email", timeout=T); shot(a, "l-pending"); step("Pending direct send: Remind (dry run) would email a masked address")
    b.goto(BASE + "#bridges"); b.reload(); expect(b.locator(f"#inc-{d}")).to_contain_text(f"{A} wants you to listen to this", timeout=T); b.click(f"[data-acc='{d}']")
    expect(b.get_by_text("Answer & rate")).to_be_visible(timeout=T); step("Direct send: recipient sees it in Pods and accepts")
    a.goto(BASE + f"#bridge/{d}/0"); a.reload(); expect(a.locator(f".remrow [data-rmd='{ib}']")).to_be_visible(timeout=T); step("After accepting: Remind shows for the unanswered partner")
    # guest partner -> in-app only (dry)
    bg = rpc(a, "create_bridge", {"p_display_name": A, "p_clip_title": f"Smoke live guest {tag}", "p_clip_url": "https://example.org/slg", "p_clip_type": "Podcast", "p_clip_cat": "", "p_clip_creator": "", "p_friend_label": "", "p_reward": ""}); bg = bg[0] if isinstance(bg, list) else bg
    rpc(g, "join_bridge", {"p_token": bg["invite_token"], "p_display_name": G})
    a.goto(BASE + f"#bridge/{bg['id']}/0"); gb = a.locator(f".remrow [data-rmd='{ig}']"); expect(gb).to_be_visible(timeout=T); gb.click()
    expect(a.locator(".toast")).to_contain_text("Dry run ✓ in-app only", timeout=T); shot(a, "l-guest"); step("Guest partner: Remind (dry run) is in-app only")
    # unused invite -> Resend invite; invite landing asks for email
    bu = rpc(a, "create_bridge", {"p_display_name": A, "p_clip_title": f"Smoke live unused {tag}", "p_clip_url": "https://example.org/slu", "p_clip_type": "Podcast", "p_clip_cat": "", "p_clip_creator": "", "p_friend_label": "", "p_reward": ""}); bu = bu[0] if isinstance(bu, list) else bu
    a.goto(BASE + f"#bridge/{bu['id']}/0"); expect(a.locator("#reinv #rsi")).to_be_visible(timeout=T); assert a.locator("[data-rmd]").count() == 0; step("Unused invite: 'Resend invite'")
    v = phone("V"); v.goto(BASE + "#b/" + bu["invite_token"]); expect(v.locator("#em")).to_be_visible(timeout=T); v.goto(BASE); v.click("#sbtn"); expect(v.locator("#em")).to_be_visible()
    shot(v, "l-signup"); step("Invite landing + Sign Up ask for name + email (not submitted)")
    # group pod
    pod = rpc(a, "create_group_pod", {"p_name": f"Smoke live pod {tag}", "p_members": [ib, ic]})
    clip = rpc(a, "share_to_group_pod", {"p_pod": pod, "p_title": f"Smoke live ep {tag}", "p_url": "https://example.org/sle", "p_kind": "Podcast", "p_note": ""})
    rpc(b, "answer_group_clip_v2", {"p_clip": clip, "p_answer": "Good one", "p_rating": 8}); rpc(a, "answer_group_clip_v2", {"p_clip": clip, "p_answer": "Agreed", "p_rating": 6})
    a.goto(BASE + f"#pod/{pod}"); expect(a.locator("#gmembers summary")).to_contain_text("1 can be reminded", timeout=T); a.click("#gmembers summary")
    a.locator(f"#gmembers [data-rmd='{ic}']").click(); expect(a.locator(".toast")).to_contain_text("Dry run ✓ would email", timeout=T)
    expect(a.locator(".gavg").first).to_contain_text("7.0/10", timeout=T); shot(a, "l-group"); step("Group pod: Remind (dry run) for the one who hasn't answered; rating average 7.0")
    assert a.evaluate("async()=>{const{count}=await sb.from('pod_reminders').select('id',{count:'exact',head:true});return count}") == 0; step("Dry runs stored no reminders")
    w = a.evaluate("document.documentElement.scrollWidth"); assert w <= 375, w
    assert not errors, errors; step("No overflow, no JS errors"); br.close()
print(f"Hosted live smoke: {n} checks passed")
