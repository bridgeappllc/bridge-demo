"""E2E (three phones): A creates a group pod with B and C (search + pick), B and C are notified, A shares a clip,
B and C are notified, chat stays locked until you answer the newest clip, group chat works across all three
(Realtime + polling), owner removes / member leaves. Users are named Smoke* so hosted runs can be cleaned up."""
import os, re, time
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/")
SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 30000; n = 0; tag = str(int(time.time()) % 100000); A, Bn, Cn = f"SmokeAva{tag}", f"SmokeBo{tag}", f"SmokeCy{tag}"
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    def phone(who):
        ctx = br.new_context(**{**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}})
        ctx.add_init_script(f"window.NTF_MS={os.environ.get('NTF_MS', '4000')}"); pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"{who}: {e}")); pg.on("dialog", lambda d: d.accept()); return pg
    def shot(pg, name): pg.wait_for_timeout(400); pg.screenshot(path=f"{SHOTS}/gp-{name}.png")
    def signup(pg, name):
        pg.goto(BASE); pg.click("#sbtn"); pg.fill("#nm", name); pg.click("#nok")
        [pg.click(f".topic[data-t={t}]") for t in ("Politics", "Science", "Culture")]; pg.click("#tgo"); expect(pg.locator("#ubtn")).to_be_visible(timeout=T)
    def answer(pg, who):
        for i in range(3): pg.locator(".gclip").first.locator(".gq").nth(i).fill(f"{who} answer {i+1}")
        pg.locator(".gclip").first.locator("[data-gans]").click(); expect(pg.locator(".toast")).to_contain_text("Answers shared", timeout=T)
    a, b, c = phone("A"), phone("B"), phone("C"); signup(a, A); signup(b, Bn); signup(c, Cn)
    # A creates the pod: search + pick two people
    a.goto(BASE + "#bridges"); expect(a.locator("#gnew")).to_be_visible(timeout=T); shot(a, "1-your-pods"); a.click("#gnew")
    a.fill("#gname", f"Smoke listeners {tag}")
    for who in (Bn, Cn):
        a.fill("#gpq", who); lab = a.locator("#gpres label", has_text=who); expect(lab).to_be_visible(timeout=T); lab.locator("input").check()
    expect(a.locator("#gcount")).to_contain_text("2 picked"); shot(a, "2-create"); a.click("#ggo")
    expect(a).to_have_url(re.compile("#pod/"), timeout=T); pod = a.url.split("#pod/")[1]
    expect(a.locator("h1")).to_have_text(f"Smoke listeners {tag}"); expect(a.get_by_text("3 of 12 people")).to_be_visible(); step("A creates a pod with B and C (search + pick, 3 of 12)")
    # B and C are notified
    for pg, who in ((b, "B"), (c, "C")):
        expect(pg.locator("#bell .nb")).to_have_text("1", timeout=T); pg.click("#bell"); row = pg.locator(".nrow", has_text="added you to the pod"); expect(row).to_contain_text(A, timeout=T)
        row.click(); expect(pg).to_have_url(re.compile("#pod/" + pod), timeout=T); expect(pg.locator("h1")).to_have_text(f"Smoke listeners {tag}", timeout=T)
    step("B and C get 'added you to the pod' notifications that open the pod")
    b.goto(BASE + "#bridges"); expect(b.locator(".gcard", has_text=f"Smoke listeners {tag}")).to_contain_text("3 people", timeout=T); step("Pod shows under 'Group pods' on Your Pods")
    # group chat before any clip
    b.goto(BASE + "#pod/" + pod); b.fill("#gct", "Hi pod from Bo"); b.click("#gcs"); expect(b.locator("#gchat .bub.me").last).to_have_text("Hi pod from Bo", timeout=T)
    a.goto(BASE + "#pod/" + pod); expect(a.locator("#gchat .bub", has_text="Hi pod from Bo")).to_be_visible(timeout=T); expect(a.locator("#gchat .who").first).to_contain_text(Bn)
    expect(c.locator("#gchat .bub", has_text="Hi pod from Bo")).to_be_visible(timeout=T); step("Group chat: B's message reaches A and C live, with sender name")
    # A shares a clip
    a.click("#gsharebtn"); a.fill("#gsurl", f"https://example.org/group-{tag}"); a.fill("#gstitle", "Smoke group episode"); a.fill("#gsnote", "Listen before Friday"); shot(a, "3-share")
    a.click("#gsgo"); expect(a.locator(".toast")).to_contain_text("Shared with the pod", timeout=T); expect(a.locator(".gclip").first).to_contain_text("Smoke group episode")
    expect(a.get_by_text("Chat locked")).to_be_visible(); step("A shares a clip; chat re-locks until A answers it")
    for pg in (b, c):
        pg.goto(BASE + "#notifications"); expect(pg.locator(".nrow", has_text="shared a clip in your pod")).to_contain_text("Smoke group episode", timeout=T)
    step("B and C are notified about the shared clip")
    b.goto(BASE + "#pod/" + pod); expect(b.get_by_text("Chat locked")).to_be_visible(timeout=T); expect(b.locator("#gchat")).to_have_count(0); shot(b, "4-locked")
    step("B's chat is locked (and hidden) until B answers")
    answer(a, "Ava"); expect(a.locator("#gchat .bub", has_text="Hi pod from Bo")).to_be_visible(timeout=T)
    a.fill("#gct", "Thoughts on the episode?"); a.click("#gcs"); expect(a.locator("#gchat .bub.me").last).to_have_text("Thoughts on the episode?", timeout=T); step("A answers -> chat unlocks -> A posts")
    answer(b, "Bo"); det = b.locator(".gclip").first.locator("details"); expect(det).to_contain_text("Ava answer 1", timeout=T); expect(b.locator("#gchat .bub", has_text="Thoughts on the episode?")).to_be_visible(timeout=T)
    b.fill("#gct", "Loved it"); b.click("#gcs"); shot(b, "5-answers-chat"); step("B answers -> sees A's answers + the chat, replies")
    c.goto(BASE + "#pod/" + pod); expect(c.get_by_text("Chat locked")).to_be_visible(timeout=T); answer(c, "Cy")
    expect(c.locator("#gchat .bub", has_text="Loved it")).to_be_visible(timeout=T); expect(c.locator(".gclip").first.locator("details")).to_contain_text("Bo answer 1"); shot(c, "6-c-chat")
    step("C answers -> sees both answers + all messages")
    def report(pg, sel, title):
        pg.locator(sel).first.click(); expect(pg.locator("#reph")).to_contain_text(title, timeout=T); pg.locator("#repsheet input[name=rr]").first.check()
        pg.click("#rsend"); expect(pg.locator(".toast")).to_contain_text("your report was sent", timeout=T)
    report(c, "#gchat [data-rep=group_message]", "a pod message from"); shot(c, "7-reported")
    report(c, ".gclip [data-rep=group_clip]", "a clip shared by")
    c.click("#gmembers summary"); report(c, "#gmembers [data-rep=user]", "Report Smoke"); report(c, "#grpod", "this pod")
    expect(c.locator(f"#gmembers [data-rep=user][data-who='{Cn}']")).to_have_count(0); expect(a.locator("#grpod")).to_have_count(0)
    step("Report: pod message, shared clip, member, and the pod (none for yourself / owner's own pod)")
    a.goto(BASE + "#notifications"); expect(a.locator(".nrow", has_text="messages in")).to_contain_text(Bn, timeout=T); step("Message notifications are grouped per pod ('N messages in …')")
    # owner removes C, B leaves
    a.goto(BASE + "#pod/" + pod); a.click("#gmembers summary"); a.locator(f"[data-grm][data-gn='{Cn}']").click(); expect(a.get_by_text("2 of 12 people")).to_be_visible(timeout=T)
    c.goto(BASE + "#pod/" + pod); expect(c.get_by_text("Pod not found")).to_be_visible(timeout=T); step("Owner removes C; C can no longer open the pod")
    b.goto(BASE + "#pod/" + pod); b.click("#gmembers summary"); b.click("#gleave"); expect(b).to_have_url(re.compile("#bridges"), timeout=T); expect(b.locator(".gcard", has_text=f"Smoke listeners {tag}")).to_have_count(0, timeout=T)
    step("B leaves the pod")
    for pg in (a, b, c):
        w = pg.evaluate("document.documentElement.scrollWidth"); assert w <= 375, w
    step("No horizontal overflow at 375px"); assert not errors, errors; step("No uncaught JS errors")
    br.close()
print(f"E2E group pods: {n} checks passed")
