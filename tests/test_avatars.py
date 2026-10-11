"""Profile photos: Storage bucket rules + profile column + RPCs + deletion, through the real HTTP APIs
(GoTrue sign-in -> Storage API / PostgREST), against the local stack (tests/local-stack, incl. storage.sh)."""
import io, os, uuid, json, requests, psycopg
from PIL import Image
API = os.environ.get("SB_URL", "http://127.0.0.1:54321"); RUN = os.environ.get("RUN", "/tmp/bridge-stack")
ANON = open(f"{RUN}/anon.key").read().strip()
db = psycopg.connect(os.environ.get("DSN", "postgresql://postgres@127.0.0.1:54322/postgres"), autocommit=True)
q = lambda sql, p=(): db.execute(sql, p).fetchall()
passed = failed = 0
def check(name, cond):
    global passed, failed
    if cond: passed += 1; print("  PASS", name)
    else: failed += 1; print("  FAIL", name)
if requests.get(f"{API}/storage/v1/status").status_code != 200:
    raise SystemExit("Storage API not running: build it and start tests/local-stack/storage.sh (see its header)")
class U:
    def __init__(s, name):
        r = requests.post(f"{API}/auth/v1/signup", headers={"apikey": ANON}, json={}); r.raise_for_status()
        d = r.json(); s.tok = d["access_token"]; s.id = d["user"]["id"]; s.name = name
        s.h = {"apikey": ANON, "Authorization": f"Bearer {s.tok}"}
        if name: s.rest("post", "profiles", json={"id": s.id, "display_name": name}).raise_for_status()
    def rest(s, m, path, **kw): return getattr(requests, m)(f"{API}/rest/v1/{path}", headers={**s.h, "Prefer": "return=minimal"}, **kw)
    def rpc(s, fn, args=None): return requests.post(f"{API}/rest/v1/rpc/{fn}", headers=s.h, json=args or {})
    def up(s, path, data, ct="image/webp", upsert=False):
        return requests.post(f"{API}/storage/v1/object/avatars/{path}", headers={**s.h, "content-type": ct, "x-upsert": "true" if upsert else "false"}, data=data)
    def rm(s, paths): return requests.delete(f"{API}/storage/v1/object/avatars", headers=s.h, json={"prefixes": paths})
    def ls(s, folder): return requests.post(f"{API}/storage/v1/object/list/avatars", headers=s.h, json={"prefix": folder, "limit": 100})
def img(color=(160, 69, 43), size=512, fmt="WEBP"):
    b = io.BytesIO(); Image.new("RGB", (size, size), color).save(b, fmt, quality=80); return b.getvalue()
pub = lambda path: requests.get(f"{API}/storage/v1/object/public/avatars/{path}")
rnd = lambda ext="webp": f"{uuid.uuid4().hex[:16]}.{ext}"
tag = uuid.uuid4().hex[:6]
A, B, C = U(f"Ann{tag}"), U(f"Ben{tag}"), U(f"Cy{tag}")

print("bucket rules (server-side)")
pa = f"{A.id}/{rnd()}"; r = A.up(pa, img())
check(f"A uploads a WebP to her own folder ({r.status_code})", r.status_code == 200)
r = pub(pa); check("anyone can load it by its (unguessable) public URL — works in <img>", r.status_code == 200 and r.content == img())
check("A uploads a JPEG too", A.up(f"{A.id}/{rnd('jpg')}", img(fmt="JPEG"), "image/jpeg").status_code == 200)
r = B.up(f"{A.id}/{rnd()}", img()); check(f"B can't upload into A's folder ({r.status_code})", r.status_code in (400, 403))
r = B.up(pa, img((0, 0, 0)), upsert=True); check(f"B can't overwrite A's file ({r.status_code})", r.status_code in (400, 403) and pub(pa).content == img())
r = B.rm([pa]); check(f"B can't delete A's file ({r.status_code}, {r.text[:40]})", pub(pa).status_code == 200)
r = B.ls(A.id); check(f"B can't list A's folder ({r.status_code}: {r.text[:30]})", r.status_code == 200 and r.json() == [])
r = A.ls(A.id); check(f"A can list her own folder ({len(r.json())} files)", r.status_code == 200 and len(r.json()) == 2)
big = os.urandom(2_200_000); r = A.up(f"{A.id}/{rnd()}", big)
check(f"file over 2 MB rejected ({r.status_code})", r.status_code in (400, 413))
r = A.up(f"{A.id}/{rnd('png')}", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"); check(f"SVG rejected ({r.status_code})", r.status_code in (400, 415))
r = A.up(f"{A.id}/{rnd('png')}", b"hello", "text/plain"); check(f"non-image MIME rejected ({r.status_code})", r.status_code in (400, 415))
r = A.up(f"{A.id}/../{B.id}/{rnd()}", img()); check(f"path tricks rejected ({r.status_code})", r.status_code >= 400)
r = A.up(f"{A.id}/sub/{rnd()}", img()); check(f"sub-folders / odd names rejected ({r.status_code})", r.status_code in (400, 403))
r = A.up(f"{A.id}/{rnd()}", img()); check("3rd file allowed (replace flow needs 2 at once)", r.status_code == 200)
r = A.up(f"{A.id}/{rnd()}", img()); check(f"4th file refused (max 3 per person) ({r.status_code})", r.status_code in (400, 403))
r = requests.post(f"{API}/storage/v1/object/avatars/{A.id}/{rnd()}", headers={"apikey": ANON, "Authorization": f"Bearer {ANON}", "content-type": "image/webp"}, data=img())
check(f"not signed in: can't upload ({r.status_code})", r.status_code in (400, 401, 403))

print("profile column")
def setav(u, v): return u.rest("patch", f"profiles?id=eq.{u.id}", json={"avatar_url": v})
v = f"{pa}?v=1760000000000"
check("A sets avatar_url to her own uploaded file", setav(A, v).status_code == 204)
r = setav(A, f"{B.id}/{rnd()}?v=1760000000000"); check(f"pointing at someone else's folder is rejected ({r.status_code})", r.status_code == 400)
r = setav(A, "https://evil.example/pixel.gif"); check(f"external URLs are rejected ({r.status_code})", r.status_code == 400)
r = setav(A, f"{A.id}/{rnd()}?v=1760000000000"); check(f"a path with no uploaded file is rejected ({r.json().get('message')})", r.status_code == 400 and "Upload the photo first" in r.text)
check("…A's avatar_url unchanged", q("select avatar_url from profiles where id=%s", (A.id,))[0][0] == v)
r = B.rest("patch", f"profiles?id=eq.{A.id}", json={"avatar_url": None}); check("B can't change A's photo", q("select avatar_url from profiles where id=%s", (A.id,))[0][0] == v)

print("who sees the photo")
r = B.rpc("avatars", {"p_ids": [A.id, C.id]}); check(f"signed-in B gets A's photo (C has none) {r.json()}", r.status_code == 200 and r.json() == [{"id": A.id, "avatar_url": v}])
r = requests.post(f"{API}/rest/v1/rpc/avatars", headers={"apikey": ANON, "Authorization": f"Bearer {ANON}"}, json={"p_ids": [A.id]})
check(f"not signed in: avatars() refused ({r.status_code})", r.status_code in (401, 403, 404))
check("A blocks C", A.rpc("block_user", {"p_user": C.id}).status_code in (200, 204))
check("C no longer gets A's photo", C.rpc("avatars", {"p_ids": [A.id]}).json() == [])
check("A doesn't get C either (blocks hide both ways)", A.rpc("avatars", {"p_ids": [C.id]}).json() == [])
r = A.rpc("create_bridge", {"p_display_name": A.name, "p_clip_title": "Photo test", "p_clip_url": f"https://example.org/p-{tag}", "p_clip_type": "Podcast"})
tok = r.json()["invite_token"]
r = requests.post(f"{API}/rest/v1/rpc/invite_avatar", headers={"apikey": ANON, "Authorization": f"Bearer {ANON}"}, json={"p_token": tok})
check(f"invite landing (anyone with the link) gets the inviter's photo", r.status_code == 200 and r.json() == v)
check("…but not someone A blocked", C.rpc("invite_avatar", {"p_token": tok}).json() is None)
check("a wrong token gets nothing", B.rpc("invite_avatar", {"p_token": "x" * 32}).json() is None)

print("reports")
r = B.rpc("report_content", {"p_type": "user", "p_id": A.id, "p_reason": "inappropriate_photo", "p_note": "photo"})
check(f"B reports A's photo ({r.status_code})", r.status_code == 200)
snap = q("select snapshot, reason from reports where id=%s", (r.json(),))[0]
check(f"report keeps the photo path in the snapshot", snap[1] == "inappropriate_photo" and f"photo: avatars/{v}" in snap[0])
r = A.rpc("report_content", {"p_type": "user", "p_id": B.id, "p_reason": "inappropriate_photo"}); check(f"can't report a photo someone doesn't have ({r.json().get('message')})", r.status_code == 400)
check("other reasons still work", A.rpc("report_content", {"p_type": "user", "p_id": B.id, "p_reason": "spam"}).status_code == 200)

print("account deletion removes the photo files")
pb = f"{B.id}/{rnd()}"; B.up(pb, img((86, 102, 76))); setav(B, f"{pb}?v=1760000000001")
files = [f"{A.id}/{o['name']}" for o in A.ls(A.id).json()]
r = A.rpc("delete_my_account"); check(f"delete_my_account refuses while photo files remain ({r.json().get('message')})", r.status_code == 400 and q("select count(*) from auth.users where id=%s", (A.id,))[0][0] == 1)
r = A.rm(files); check(f"the app removes all of A's files via the Storage API ({len(files)})", r.status_code == 200 and A.ls(A.id).json() == [])
check("account deletion then succeeds", A.rpc("delete_my_account").status_code in (200, 204) and q("select count(*) from auth.users where id=%s", (A.id,))[0][0] == 0)
check("A's photo URL no longer serves", pub(pa).status_code in (400, 404))
check("no storage rows left for A", q("select count(*) from storage.objects where bucket_id='avatars' and name like %s", (A.id + "/%",))[0][0] == 0)
check("B's photo + profile untouched", pub(pb).status_code == 200 and q("select avatar_url from profiles where id=%s", (B.id,))[0][0] == f"{pb}?v=1760000000001")
check("the report about A is kept (FK set null), with the photo path", q("select count(*) from reports where reason='inappropriate_photo' and snapshot like %s", (f"%{A.id}/%",))[0][0] == 1)
# cleanup (local only)
B.rm([pb])
for u in (B, C): db.execute("delete from auth.users where id=%s", (u.id,))
print(f"{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
