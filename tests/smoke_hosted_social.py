"""Hosted-safe smoke test for social features (2 anonymous sign-ups, no email): @username
suggestion + reserved name refused, search by @username, request, badge, accept, friend's library,
Discover, bridge with a friend from their item, 'Only me' privacy.  BASE=<site url>"""
import os, re, time
from playwright.sync_api import sync_playwright, expect
B=os.environ.get("BASE","https://bridgeappllc.github.io/bridge-demo/"); T=25000; errs=[]; bad=[]; tag=str(int(time.time())%100000)
A,Bn=f"SmokeAlice{tag}",f"SmokeBob{tag}"
with sync_playwright() as p:
    br=p.chromium.launch(); ip=p.devices["iPhone 13"]
    def pg(w):
        x=br.new_context(**ip).new_page(); x.on("dialog",lambda d:d.accept()); x.on("pageerror",lambda e:errs.append(f"{w}: {e}"))
        x.on("response",lambda r: bad.append(f"{w} {r.status} {r.url[:100]}") if r.status>=400 and "/rest/" in r.url else None); return x
    def signup(x,n): x.goto(B); x.click("#sbtn"); x.fill("#nm",n); x.click("#nok"); expect(x.get_by_text("Pick your topics")).to_be_visible(timeout=T); x.click("text=Skip")
    a,b=pg("a"),pg("b")
    signup(a,A); a.goto(B+"#profile"); a.click("[data-pt=Add]"); a.fill("#aurl",f"https://example.org/smoke-social-{tag}"); a.fill("#atitle","Smoke social favorite"); a.select_option("#acat","Science"); a.click("#asave"); expect(a.get_by_text("Remove from Library")).to_be_visible(timeout=T)
    a.goto(B+"#profile"); a.click("[data-pt=Settings]"); expect(a.locator("#puser")).to_have_value(re.compile(r"^smokealice\d+$"),timeout=T); h=a.locator("#puser").input_value(); a.fill("#puser","support"); expect(a.locator("#uhint")).to_contain_text("not available",timeout=T); a.fill("#puser",h); a.click("#pubsave"); expect(a.locator(".handle").first).to_have_text("@"+h,timeout=T); print("✓ A: library item; suggested @"+h+" claimed; reserved name refused")
    signup(b,Bn); b.goto(B+"#people"); b.fill("#pq","@"+h); expect(b.locator("#pres .person",has_text=A)).to_be_visible(timeout=T); b.goto(B+"#u/@"+h); expect(b.get_by_text(f"{A}'s library is for friends")).to_be_visible(timeout=T)
    b.click("#fbtns [data-fa=add]"); expect(b.locator("#fbtns")).to_contain_text("Requested",timeout=T); print("✓ B finds A by @username, library locked, sends request")
    a.goto(B+"#people"); a.reload(); expect(a.locator("#nbadge")).to_have_text("1",timeout=T); a.locator(".person",has_text=Bn).locator("[data-fa=accept]").click(); expect(a.locator(".toast")).to_contain_text("friends",timeout=T); print("✓ A sees badge, accepts")
    b.goto(B+"#u/@"+h); b.reload(); expect(b.locator(".card",has_text="Smoke social favorite")).to_be_visible(timeout=T); b.goto(B+"#profile"); b.click("[data-pt=Discover]"); expect(b.locator(".card",has_text="Smoke social favorite")).to_contain_text(f"{A}'s library",timeout=T); print("✓ B sees A's library + Discover")
    b.goto(B+"#u/@"+h); b.locator(".card",has_text="Smoke social favorite").click(); b.click(f"text=Meet {A} on the Bridge with this"); expect(b.locator("#direct")).to_be_visible(timeout=T); b.click("#mgo"); expect(b.locator("#addednote")).to_be_visible(timeout=T)
    a.goto(B+"#bridges"); a.reload(); expect(a.locator(".card",has_text=f"Invited by {Bn}")).to_be_visible(timeout=T); print("✓ bridge started from friend's item; A added directly")
    a.goto(B+"#profile"); a.click("[data-pt=Settings]"); a.check("input[name=vis][value=private]"); expect(a.locator(".toast")).to_contain_text("Only me",timeout=T)
    b.goto(B+"#u/@"+h); b.reload(); expect(b.get_by_text(f"{A} keeps their library private")).to_be_visible(timeout=T); print("✓ privacy 'Only me' hides it from friend")
    assert not errs, errs; assert not bad, bad; print("✓ no JS errors / failed API calls"); br.close()
print("Hosted social smoke: done")
