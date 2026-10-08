# Bridge v1 — going live with a real backend

## Status (Oct 8, 2026)

- ✅ Supabase project **`bridge`** created on the **Free** plan ($0/month) in org `bridgeappllc`. Region **us-west-1**, ref `gozjxubvvzxkkoxxvldo`, URL `https://gozjxubvvzxkkoxxvldo.supabase.co`.
- ✅ Schema applied as migration `bridge_v1` (`supabase/migrations/20261008000000_bridge_v1.sql`). The security advisor reports no issues. Realtime is enabled for messages, members, answers, and ratings.
- ✅ `index.html` config is filled in with the project URL and the **publishable** key.
- ✅ Anonymous sign-ins are on (Paul turned this on in the dashboard).
- ✅ The hosted two-phone smoke test passes, including Realtime. `real-backend` is merged to `main`, and https://bridgeappllc.github.io/bridge-demo/ is the real app. The old prototype is at `/bridge-demo/demo.html`.

Backend: **Supabase** (free tier): Postgres + row-level security + anonymous sign-ins + realtime.
The frontend stays a single static `index.html` on GitHub Pages.

## What we need from Paul (about 10 minutes, free, no card)

1. **Create a Supabase account**: https://supabase.com → *Start your project*. "Continue with GitHub" using the `bridgeappllc` GitHub account works fine.
2. **Create a project**: *New project* → Name `bridge` → set a database password (save it in your password manager; we don't need it) → Region: closest to your users (e.g. *West US*) → Free plan → keep **Enable Data API** checked → *Create new project*. Wait ~2 minutes.
3. **Turn on anonymous sign-ins**: *Authentication → Sign In / Providers* (called *Sign In / Up* in some dashboards) → turn on **Allow anonymous sign-ins** → *Save*. Friends join without email or password; that's how the app signs them in.
4. **Run the database setup** (already done for project `bridge`): *SQL Editor → New query* → paste all of [`supabase/schema.sql`](supabase/schema.sql) → *Run*. You should see "Success. No rows returned". (Or hand over dashboard access and we'll do this step.)
5. **Send over these two values** (from the **Connect** button at the top of the dashboard, or *Project Settings → API Keys* / *Data API*):
   - **Project URL**: `https://<something>.supabase.co`
   - **Publishable key**: starts with `sb_publishable_…`. The legacy **anon public** key (`eyJ…`) also works.

   Both are safe to put in a public web page. **Do not** send the `secret` / `service_role` key or the database password.

Optional: *Authentication → URL Configuration → Site URL* = `https://bridgeappllc.github.io/bridge-demo/`. This only matters later, for email sign-in links.

## Going live once those exist (we do this part)

1. On branch `real-backend`, fill in the config block at the top of `index.html`:
   ```js
   window.BRIDGE_CONFIG = { SUPABASE_URL: "https://xxxx.supabase.co", SUPABASE_ANON_KEY: "sb_publishable_..." };
   ```
   Commit and push.
2. Smoke test against the real project: `python3 tests/serve.py 8081` (with no `SB_KEY`, it serves the real config), then `BASE=http://127.0.0.1:8081/ REALTIME=1 python3 tests/e2e_two_users.py`. Afterwards, delete the test rows with `tests/cleanup_test_data.sql`, which removes users named `Smoke*` and everything they created.
3. Open a PR from `real-backend` to `main` and merge it. GitHub Pages redeploys in about a minute at https://bridgeappllc.github.io/bridge-demo/. The old clickable prototype stays at `/bridge-demo/demo.html`.
4. Text Paul a real invite link to try on his phone.

## How v1 works

- Visitors get a Supabase **anonymous user** when they enter their name, with no email or password. The session stays saved in that browser.
- **Create bridge** (pasted link or library clip + friend's name) → the server makes a bridge with a random 32-character invite token → the invite text includes `https://bridgeappllc.github.io/bridge-demo/#b/<token>`. `?b=<token>` also works.
- The **friend opens the link**, sees "Paul invited you…", types a name, and joins. Each bridge holds at most 2 people.
- Each person **answers 3 questions** (final once submitted). You see the other person's answers only after you submit yours. **Ratings** (0–10) work the same way. **Chat** opens for you after you rate. Messages are stored and show up for the other person within about 4 seconds (realtime when it's available, with polling as a fallback).
- **Your Bridges** lists your real bridges with both people's progress.
- **Security**: row-level security, so only members can read a bridge, its answers, ratings, or chat. Joining requires the token. Nobody can write as someone else or edit answers and ratings. All of this is in `supabase/schema.sql`.

## Known v1 limits (to tune later)

- **Guest accounts are per browser.** Clearing site data or switching phone/browser means you can't reach your old bridges. Next step: let people optionally add an email (Supabase supports converting anonymous users with `updateUser({email})`, which needs manual identity linking turned on).
- Library / Add / Discover are still device-local, and the example clips are fictional (labeled *Example*). The two example bridges and the simulated "Sam" replies are gone.
- Listen reward is a "coming soon" field. It only adds a line to the invite, and no payments happen.
- Supabase free tier: projects pause after about a week with no activity (one click to resume). Anonymous sign-ins are limited to 30 per hour per IP by default (adjustable under *Authentication → Rate Limits*). Consider turning on CAPTCHA if abuse shows up.
- `schema.sql` drops and recreates the Bridge tables. Re-running it **wipes data**, so after launch, make changes as new migration files instead.

## Tests (no Supabase account needed)

`tests/run_all.sh` starts a local Supabase-compatible stack: real PostgreSQL 17, the real Supabase Auth (GoTrue v2.197.0) binary, the real PostgREST v16.4 binary, and a small Node gateway in place of Kong. Then it runs:
- `tests/test_rls.py`: 50 SQL-level checks of the RLS policies and RPCs (outsiders, wrong token, a third joiner, reveal rules, chat lock, forging, editing).
- `tests/e2e_two_users.py`: Playwright with two separate phone-sized browser contexts going through create → invite link → join → answer → rate → chat both ways, plus persistence after reload, a full bridge, a bogus token, and an outsider.

These tests don't cover Supabase Realtime (the polling fallback was exercised instead), Supabase's hosted dashboard and API gateway, or the hosted defaults.
