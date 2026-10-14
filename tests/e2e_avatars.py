"""E2E for profile photos: pick -> square crop -> resize -> preview -> upload; replace; shown to others
(invite landing, bridge card, chat, search, profile); report a photo; remove; account deletion removes the files.
  BASE=<app url> (default local). SHOTS_DIR for screenshots. DB checks only against the local stack."""
import io, os, re, uuid, requests
from PIL import Image
from playwright.sync_api import sync_playwright, expect
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/"); LOCAL = "127.0.0.1" in BASE or "localhost" in BASE
HERE = os.path.dirname(os.path.abspath(__file__)); SHOTS = os.environ.get("SHOTS_DIR") or os.path.join(HERE, "shots"); os.makedirs(SHOTS, exist_ok=True)
T = 25000; tag = uuid.uuid4().hex[:4]; A, B = f"SmokePia{tag}", f"SmokeQuin{tag}"
db = None
if LOCAL:
    import psycopg; db = psycopg.connect(os.environ.get("DSN", "postgresql://postgres@127.0.0.1:54322/postgres"), autocommit=True)
q = lambda sql, p=(): db.execute(sql, p).fetchall()
n = 0
def step(s):
    global n; n += 1; print("  ✓", s, flush=True)
tmp = f"/tmp/bridge-avatar-test-{uuid.uuid4().hex[:6]}"; os.makedirs(tmp)
# landscape photo: red | green (centre square) | blue  -> a centre crop must be all green
im = Image.new("RGB", (1200, 800), (40, 140, 60)); im.paste((200, 30, 30), (0, 0, 200, 800)); im.paste((30, 30, 200), (1000, 0, 1200, 800))
im.save(f"{tmp}/landscape.jpg", quality=92)
# big noisy portrait PNG (~>6 MB): must be shrunk on the device to fit the 2 MB limit
Image.frombytes("RGB", (1600, 1600), os.urandom(1600 * 1600 * 3)).save(f"{tmp}/big.png")
assert os.path.getsize(f"{tmp}/big.png") > 6_000_000
open(f"{tmp}/notes.txt", "w").write("not a photo")
def gone(url, wait=90):
    """Deleted at the origin? (cache-busting query so a CDN copy can't mask it; short retry for propagation)"""
    import time; end = time.time() + wait
    while True:
        c = requests.get(url + ("&" if "?" in url else "?") + "nocache=" + uuid.uuid4().hex).status_code
        if c in (400, 404) or time.time() > end: return c in (400, 404)
        time.sleep(3)
def fetch(url):
    r = requests.get(url); assert r.status_code == 200, (url, r.status_code); return Image.open(io.BytesIO(r.content)), r.headers.get("content-type"), len(r.content)
with sync_playwright() as p:
    br = p.chromium.launch(); dev = p.devices["iPhone 13"]; errors = []
    ac, bc = br.new_context(**dev), br.new_context(**dev); pa, pb = ac.new_page(), bc.new_page()
    for pg, w in ((pa, "pia"), (pb, "quin")):
        pg.on("pageerror", lambda e, w=w: errors.append(f"{w}: {e}")); pg.on("dialog", lambda d: d.accept())
    shot = lambda pg, nm: pg.screenshot(path=f"{SHOTS}/{nm}.png")
    def signup(pg, nm):
        pg.goto(BASE); pg.click("#sbtn"); pg.fill("#nm", nm); pg.click("#nok"); expect(pg.get_by_text("Pick your topics")).to_be_visible(timeout=T)
        pg.click("text=Skip"); expect(pg.get_by_text("Your Pods")).to_be_visible(timeout=T)
    def choose(pg, trigger, path):
        with pg.expect_file_chooser() as fc: pg.click(trigger)
        fc.value.set_files(path)
    signup(pa, A)
    pa.goto(BASE + "#profile"); expect(pa.locator("#avbtn")).to_be_visible(timeout=T)
    expect(pa.locator("#avbtn")).to_have_attribute("aria-label", "Add profile photo"); assert pa.locator("#avbtn .av img").count() == 0
    # not a photo -> friendly message, nothing uploaded
    choose(pa, "#avbtn", f"{tmp}/notes.txt"); expect(pa.locator(".toast")).to_contain_text("JPG, PNG or WebP", timeout=T); assert pa.locator("#avsheet").count() == 0
    # tap the avatar -> pick -> preview
    choose(pa, "#avbtn", f"{tmp}/landscape.jpg"); expect(pa.locator("#avsheet img.avprev")).to_be_visible(timeout=T)
    expect(pa.locator("#avsheet img.avprev")).to_have_attribute("alt", "Preview of your new profile photo"); shot(pa, "av-01-preview")
    pa.click("#avno"); expect(pa.locator("#avsheet")).to_have_count(0); assert pa.evaluate("PROFILE.avatar_url") is None
    step("Tap avatar -> pick a photo -> square preview sheet (Cancel keeps nothing); a non-image gets a friendly message")
    choose(pa, "#avbtn", f"{tmp}/landscape.jpg"); expect(pa.locator("#avsheet")).to_be_visible(timeout=T); pa.click("#avuse")
    expect(pa.locator(".toast")).to_have_text("Profile photo updated", timeout=T); expect(pa.locator("#avsheet")).to_have_count(0)
    hdr = pa.locator("#avbtn .av img"); expect(hdr).to_have_attribute("alt", f"Profile photo of {A}", timeout=T)
    expect(pa.locator("#avbtn")).to_have_attribute("aria-label", "Change profile photo")
    url1 = hdr.get_attribute("src"); assert re.search(r"/storage/v1/object/public/avatars/[0-9a-f-]{36}/[0-9a-f]{16}\.(webp|jpg)\?v=\d+$", url1), url1
    pa.wait_for_function("document.querySelector('#avbtn .av img').naturalWidth>0", timeout=T)
    img1, ct, size1 = fetch(url1)
    px = [img1.convert("RGB").getpixel(xy) for xy in ((3, 3), (508, 3), (256, 256), (3, 508), (508, 508))]
    assert img1.size == (512, 512) and ct in ("image/webp", "image/jpeg") and all(g > 100 and r < 90 and b < 110 for r, g, b in px), (img1.size, ct, px)
    files1 = pa.evaluate("API.myPhotoFiles()"); assert len(files1) == 1, files1
    shot(pa, "av-02-profile-photo")
    step(f"Use photo -> uploaded as a 512×512 {ct.split('/')[1].upper()} ({size1 // 1024} KB), centre-cropped, shown in the profile header with alt text")
    # replace with a big PNG via Settings
    pa.click(".tabs button:has-text('Settings')"); expect(pa.locator("#avcard")).to_be_visible(timeout=T); expect(pa.locator("#avdel")).to_be_visible()
    choose(pa, "#avchg", f"{tmp}/big.png"); expect(pa.locator("#avsheet")).to_be_visible(timeout=T); pa.click("#avuse")
    expect(pa.locator("#avsheet")).to_have_count(0, timeout=T); expect(pa.locator("#avcard .av img")).not_to_have_attribute("src", url1, timeout=T)
    url2 = pa.locator("#avcard .av img").get_attribute("src")
    img2, ct2, size2 = fetch(url2); assert img2.size == (512, 512) and size2 < 2_000_000
    files2 = pa.evaluate("API.myPhotoFiles()"); assert len(files2) == 1 and files2 != files1, (files1, files2)
    assert gone(url1), "old photo should be deleted"
    if db: assert q("select count(*) from storage.objects o join profiles p on split_part(o.name,'/',1)=p.id::text where p.display_name=%s", (A,)) == [(1,)]
    step(f"Settings > Change photo: a 6+ MB PNG is shrunk on the device ({size2 // 1024} KB) and replaces the old one (old file deleted)")
    # B: invite landing, bridge card, chat, search, profile
    pa.goto(BASE + "#new"); pa.fill("#murl", "https://example.org/avatar-test"); pa.fill("#mtitle", "Avatar test"); pa.fill("#mfriend", B)
    pa.click("#mgo"); expect(pa.locator("#itxt")).to_be_visible(timeout=T)
    link = re.search(r"(https?://\S+#b/[0-9a-f]{32})", pa.locator("#itxt").input_value()).group(1)
    pb.goto(link); expect(pb.locator(".inv .av img")).to_have_attribute("alt", f"Profile photo of {A}", timeout=T)
    pb.wait_for_function("document.querySelector('.inv .av img')&&document.querySelector('.inv .av img').naturalWidth>0", timeout=T); shot(pb, "av-03-invite-landing")
    step("Invite landing (before the friend has an account) shows the inviter's photo")
    pb.fill("#jname", B); pb.click("#jgo"); expect(pb.get_by_text("Answer & rate")).to_be_visible(timeout=T)
    for pg in (pb, pa):
        if pg is pa: pa.click("#nx"); expect(pa.get_by_text("Answer & rate")).to_be_visible(timeout=T)
        pg.fill("#q3", f"Answer number takeaway"); pg.locator('.rate [data-rv="7"]').click()
        pg.click("#qsave"); expect(pg.get_by_text("💬 Talk")).to_be_visible(timeout=T)
    pa.fill("#ct", "Hi from Pia"); pa.click("#cs")
    expect(pb.locator(".who .av img")).to_have_attribute("alt", f"Profile photo of {A}", timeout=T)
    pb.goto(BASE + "#bridges"); expect(pb.locator(".bcrow .av img").first).to_have_attribute("alt", f"Profile photo of {A}", timeout=T); shot(pb, "av-04-bridges")
    a_id = files2[0].split("/")[0]
    pb.goto(BASE + f"#u/{a_id}"); expect(pb.locator(".c .av img").first).to_have_attribute("alt", f"Profile photo of {A}", timeout=T)
    pb.goto(BASE + "#people"); pb.fill("#pq", A); expect(pb.locator(f".person[data-person='{a_id}'] .av img")).to_be_visible(timeout=T)
    step("The other person sees the photo in chat, on bridge cards, on the profile page and in people search")
    pb.goto(BASE + f"#u/{a_id}"); expect(pb.locator("#repu")).to_be_visible(timeout=T); pb.click("#repu")
    expect(pb.locator("#repsheet label:has-text('Inappropriate profile photo')")).to_be_visible(); pb.click("#repsheet label:has-text('Inappropriate profile photo')")
    pb.click("#rsend"); expect(pb.locator(".toast")).to_contain_text("Thanks", timeout=T)
    if db: assert q("select r.reason, r.snapshot like '%%photo: avatars/%%' from reports r join profiles p on p.id=r.target_user where p.display_name=%s", (A,)) == [("inappropriate_photo", True)]
    step("Report a profile: 'Inappropriate profile photo' is offered when they have one (report keeps the photo path)")
    # A removes the photo
    pa.goto(BASE + "#profile"); pa.click(".tabs button:has-text('Settings')"); expect(pa.locator("#avdel")).to_be_visible(timeout=T); pa.click("#avdel")
    expect(pa.locator(".toast")).to_have_text("Profile photo removed", timeout=T); expect(pa.locator("#avdel")).to_have_count(0)
    assert pa.locator("#avcard .av img").count() == 0 and pa.evaluate("API.myPhotoFiles()") == [] and gone(url2)
    pb.goto(BASE + f"#u/{a_id}"); pb.reload(); expect(pb.locator("h1")).to_have_text(A, timeout=T); assert pb.locator(".c .av img").count() == 0
    step("Remove photo: back to the initial everywhere, file deleted from Storage")
    # photo again, then delete account -> files gone
    choose(pa, "#avchg", f"{tmp}/landscape.jpg"); expect(pa.locator("#avsheet")).to_be_visible(timeout=T); pa.click("#avuse"); expect(pa.locator("#avsheet")).to_have_count(0, timeout=T); expect(pa.locator("#avcard .av img")).to_be_visible(timeout=T)
    url3 = pa.locator("#avcard .av img").get_attribute("src"); assert requests.get(url3).status_code == 200
    pa.click("#delbtn"); expect(pa.locator("#delc")).to_be_visible(); pa.fill("#delc", "DELETE"); pa.click("#delyes"); expect(pa.locator("#sbtn")).to_be_visible(timeout=T)
    assert gone(url3), "photo must be deleted with the account"
    if db: assert q("select count(*) from storage.objects where name like %s", (a_id + "/%",)) == [(0,)] and q("select count(*) from auth.users where id=%s", (a_id,)) == [(0,)]
    step("Delete account also deletes the photo files (URL stops working)")
    assert not errors, errors; step("No uncaught JS errors")
    # B tidies up: delete B's account too (so live smoke leaves no files)
    pb.goto(BASE + "#profile"); pb.click(".tabs button:has-text('Settings')"); pb.click("#delbtn"); pb.fill("#delc", "DELETE"); pb.click("#delyes"); expect(pb.locator("#sbtn")).to_be_visible(timeout=T)
    br.close()
print(f"E2E avatars: {n} checks passed")
