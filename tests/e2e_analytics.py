"""E2E analytics (LOCAL or hosted-safe, no email): key actions log first-party events for the user's own id only,
users can't read/forge events or call admin_stats, the Stats menu/screen is admin-only. Smoke* accounts via hosted_users.
On hosted, the operator confirms the users and makes nobody an admin; the admin part runs only locally."""
import os, time
from hosted_users import make, confirm
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); LOCAL = "127.0.0.1" in BASE; T = 30000; n = 0; tag = str(int(time.time()) % 100000)
SHOTS = os.environ.get("SHOTS_DIR", "/tmp/shots-analytics"); os.makedirs(SHOTS, exist_ok=True)
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
def mine(pg):  # events are write-only for users: count via the DB locally, else trust the insert result
    return pg.evaluate("async()=>(await sb.from('events').select('id')).data")
with sync_playwright() as p:
    br = p.chromium.launch(); errors = []
    dev = {**p.devices["iPhone 13"], "viewport": {"width": 375, "height": 760}}
    a = br.new_context(**dev).new_page(); b = br.new_context(**dev).new_page()
    for pg in (a, b): pg.on("pageerror", lambda e: errors.append(str(e))); pg.on("dialog", lambda d: d.accept())
    ia = make(a, BASE, f"SmokeAn{tag}"); ib = make(b, BASE, f"SmokeAnB{tag}"); confirm(BASE, [(a, ia), (b, ib)])
    a.goto(BASE + "#bridges"); a.wait_for_timeout(1500)
    r = a.evaluate("async()=>API.createBridge({title:'Smoke clip',url:'https://open.spotify.com/episode/an"+tag+"',type:'Podcast'})")
    tok = r[0]["invite_token"] if isinstance(r, list) else r["invite_token"]; bid = r[0]["id"] if isinstance(r, list) else r["id"]
    a.evaluate("async()=>API.addLib({url:'https://open.spotify.com/episode/lib"+tag+"',title:'Lib "+tag+"'})")
    b.goto(BASE + "#bridges"); b.wait_for_timeout(1500)
    b.evaluate(f"async()=>API.join('{tok}',PROFILE.display_name)"); b.evaluate(f"async()=>API.answer('{bid}','Great point',8)"); b.evaluate(f"async()=>API.send('{bid}','hello from smoke')")
    a.wait_for_timeout(1500); step("Actions done: pod, library add, join, answer, message")
    assert not mine(a) and not mine(b), "users must not read events"; step("Users can't read events (RLS)")
    e = a.evaluate(f"async()=>(await sb.from('events').insert({{user_id:'{ib}',name:'app_open'}})).error")
    assert e, "forged user_id must fail"; step("Can't insert an event for another user")
    e = a.evaluate("async()=>(await sb.from('events').insert({name:'evil'})).error"); assert e; step("Unknown event names rejected")
    e = a.evaluate("async()=>(await sb.from('events').insert({name:'app_open',props:{x:'y'.repeat(2000)}})).error"); assert e; step("Oversized props rejected")
    e = a.evaluate("async()=>(await sb.rpc('admin_stats')).error"); assert e and e["code"] == "42501", e; step("Non-admin: admin_stats refused (42501)")
    assert a.evaluate("async()=>(await sb.rpc('is_stats_admin')).data") is False
    a.goto(BASE + "#bridges"); a.screenshot(path=f"{SHOTS}/menu-pre.png"); a.click("#ubtn"); expect(a.locator("#umenu")).to_be_visible(timeout=T); assert a.locator("[data-um='stats']").count() == 0; a.keyboard.press("Escape")
    a.goto(BASE + "#stats"); expect(a.get_by_text("This page is for admins.")).to_be_visible(timeout=T); step("Non-admin: no Stats menu item, #stats shows nothing")
    if LOCAL:
        import psycopg; db = psycopg.connect("postgresql://postgres@127.0.0.1:54322/postgres", autocommit=True)
        got = lambda u: sorted(r[0] for r in db.execute("select name from events where user_id=%s", (u,)))
        ga, gb = got(ia), got(ib)
        for want in ("app_open", "pod_created", "clip_shared", "library_add"): assert want in ga, (want, ga)
        for want in ("app_open", "invite_joined", "answer_submitted", "message_sent"): assert want in gb, (want, gb)
        step(f"Events logged: A={ga} B={gb}")
        em = db.execute("select email from auth.users where id=%s", (ia,)).fetchone()[0]; db.execute("insert into stats_admins values (%s)", (em,))
        try:
            a.goto(BASE + "#bridges"); a.reload(); a.wait_for_function("ADMIN===true", timeout=T)
            a.click("#ubtn"); a.click("[data-um='stats']"); expect(a.locator("h1", has_text="Stats")).to_be_visible(timeout=T); expect(a.get_by_text("Total sign-ups")).to_be_visible(timeout=T)
            s = a.evaluate("async()=>(await sb.rpc('admin_stats')).data")
            for k in ("dau","wau","mau","total_signups","signups_per_week","pods_created","clips_shared","answers","messages","avg_rating","retention_7d","retention_30d"): assert k in s, k
            assert s["dau"] >= 0 and len(s["signups_per_week"]) == 8
            a.screenshot(path=f"{SHOTS}/stats-local.png", full_page=True); step(f"Admin: Stats menu + screen; RPC returns all metrics (total_signups={s['total_signups']}, dau={s['dau']})")
        finally: db.execute("delete from stats_admins where email=%s", (em,))
    assert not errors, errors; step("No JS errors"); br.close()
print(f"E2E analytics: {n} checks passed")
