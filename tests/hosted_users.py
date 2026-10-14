"""Hosted-safe test users (no sign-up form, no code emails). Each Smoke* user gets a session in its own page
(anonymous sign-in + profile, via the app's own client), then the operator gives it a confirmed @example.invalid
email out-of-band (SQL on hosted; done directly against the local DB when BASE is local), and the page refreshes
its session so it's a normal email account. Clean up Smoke* users afterwards."""
import json, os, time
HANDOFF = os.environ.get("HANDOFF", "/tmp/hosted-users")
MK = "async n=>{const{data,error}=await sb.auth.signInAnonymously();if(error)throw error;const r=await sb.from('profiles').insert({id:data.user.id,display_name:n,topics:['Science','Culture','Politics']});if(r.error)throw r.error;return data.user.id}"
def make(pg, base, name):
    pg.goto(base); pg.wait_for_function("typeof sb!=='undefined'"); return pg.evaluate(MK, name)
def confirm(base, pages_ids):
    ids = [i for _, i in pages_ids]
    if "127.0.0.1" in base:
        import psycopg; db = psycopg.connect("postgresql://postgres@127.0.0.1:54322/postgres", autocommit=True)
        for i in ids: db.execute("update auth.users set email='smoke-'||left(id::text,8)||'@example.invalid', email_confirmed_at=now(), is_anonymous=false where id=%s", (i,))
    else:
        for f in (HANDOFF + ".ok",):
            if os.path.exists(f): os.remove(f)
        open(HANDOFF + ".ids", "w").write(json.dumps(ids)); print("    waiting for operator to confirm", ids, flush=True)
        for _ in range(900):
            if os.path.exists(HANDOFF + ".ok"): break
            time.sleep(1)
        else: raise AssertionError("operator never confirmed")
        os.remove(HANDOFF + ".ok"); os.remove(HANDOFF + ".ids")
    for pg, _ in pages_ids:
        pg.evaluate("async()=>{const{error}=await sb.auth.refreshSession();if(error)throw error}"); pg.reload()
        pg.wait_for_function("typeof USER!=='undefined'&&USER&&USER.is_anonymous===false", timeout=30000)
