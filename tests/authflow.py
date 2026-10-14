"""Shared e2e helpers: email sign-up (name + email + emailed code) against the LOCAL stack's mail catcher.
Guest sign-in is gone from the UI, so every test user signs up with an @test.local address."""
import json, os, re, time, random, urllib.request, urllib.parse
from playwright.sync_api import expect
MAILPIT = os.environ.get("MAILPIT", "http://127.0.0.1:8025"); T = 30000
def mails(addr): return json.load(urllib.request.urlopen(f"{MAILPIT}/api/v1/search?query=to:{urllib.parse.quote(addr)}"))["messages"]
def code_for(addr, before=0):
    for _ in range(60):
        m = mails(addr)
        if len(m) > before:
            g = re.search(r"(\d{6,10})", m[0]["Subject"])
            if g: return g.group(1)
        time.sleep(0.5)
    raise AssertionError("no code email for " + addr)
def email_for(name): return f"{re.sub(r'[^a-z0-9]', '', name.lower()) or 'user'}-{random.randint(10**5, 10**6)}@test.local"
def _code(pg, email, before):
    expect(pg.locator("#code")).to_be_visible(timeout=T); pg.fill("#code", code_for(email, before)); pg.click("#cok")
def signup_email(pg, name, email=None):
    """Welcome -> (Sign Up Free already clicked) -> name + email -> code. Returns the email."""
    email = email or email_for(name); before = len(mails(email))
    pg.fill("#nm", name); pg.fill("#em", email); pg.click("#nok"); _code(pg, email, before); return email
def join_email(pg, name, email=None):
    """Invite landing: name + email -> code -> joined (when not signed in); signed-in users just join."""
    if pg.locator("#em").count() == 0: pg.fill("#jname", name); pg.click("#jgo"); return None
    email = email or email_for(name); before = len(mails(email))
    pg.fill("#jname", name); pg.fill("#em", email); pg.click("#jgo"); _code(pg, email, before); return email
