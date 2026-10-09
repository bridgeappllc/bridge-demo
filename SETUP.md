# Bridge — setup & status

Live: https://bridgeappllc.github.io/bridge-demo/ (old prototype: `/bridge-demo/demo.html`).
Backend: **Supabase** project `bridge` (Free plan, $0) — ref `gozjxubvvzxkkoxxvldo`, us-west-1.
Frontend: one static `index.html` on GitHub Pages (config block at the top: project URL + publishable key).

## Status (Oct 8, 2026)

- ✅ v1 (Oct 8): real bridges — invite link, guest join with a name, 3 answers + rating with reveal, stored chat with realtime, Your Bridges.
- ✅ v2: **online Library** + **email sign-in** (migration `library_and_community`, file `supabase/migrations/20261008160000_library_and_community.sql`).
- ✅ **Email sign-in is fully configured (Oct 8, 2026, ~8:20 PM HST)** via the Supabase Management API:
  - Custom SMTP through **Resend**: host `smtp.resend.com`, port 465, user `resend`, password = a sending-only Resend API key; sender **Bridge &lt;hello@meetonthebridge.org&gt;**. Domain `meetonthebridge.org` is verified in Resend (DNS at GoDaddy).
  - Email rate limit: 30 emails/hour (was 2). Raise at https://supabase.com/dashboard/project/gozjxubvvzxkkoxxvldo/auth/rate-limits if needed.
  - Templates: **Magic Link** = `supabase/email-templates/magic_link.html`, subject `{{ .Token }} is your Bridge sign-in code`; **Change Email Address** = `supabase/email-templates/email_change.html`, subject `{{ .Token }} is your Bridge confirmation code`.
  - Site URL `https://bridgeappllc.github.io/bridge-demo/`, also in Redirect URLs.
  - Nothing else changed. A copy of the previous auth settings (no secrets) is at `/workspace/bridge-ops/auth_config_backup_2026-10-08.json` on the work box.
  - Codes are **8 digits** (the project's *Email OTP length* setting); the app accepts 6–10 digits.

## Email settings reference

- SMTP: https://supabase.com/dashboard/project/gozjxubvvzxkkoxxvldo/auth/smtp
- Templates: https://supabase.com/dashboard/project/gozjxubvvzxkkoxxvldo/auth/templates
- URL configuration: https://supabase.com/dashboard/project/gozjxubvvzxkkoxxvldo/auth/url-configuration
- Resend dashboard (sending logs, domain status): https://resend.com/emails
- If you rotate the Resend key, paste the new one as the SMTP password on the SMTP page.

## How it works

- **Guests by default.** Entering a name creates a Supabase anonymous user (no email, no password), saved in that browser.
- **Save your account (optional).** Shown after you start a bridge, after a friend joins, on Your Bridges, and in Profile → Settings. You enter an email, get a one-time code (8 digits), type it in. The guest account is converted *in place* (`updateUser({email})` + `verifyOtp(type: email_change)`), so the same user keeps every bridge, answer, chat and library item.
- **I have an account** (welcome screen, and on invite pages): email → code → signed in (`signInWithOtp` with `shouldCreateUser: false` + `verifyOtp(type: email)`); your bridges, library, name and topics come back. Unknown emails get "No Bridge account uses that email yet" — no account is created.
- **Library** (Profile → Library / Add): link, title, category, personal note, stored in `library_items` with RLS. You can read/write your own; people you share a bridge with can view (not edit) it via "Friends' libraries" chips or the link in a bridge. You can add a friend's item to your own library or start a bridge from any item. Old device-local library items are imported into the account on first load.
- **Community rating** on a link = average of real bridge ratings for that URL, shown only once 3+ people have rated it (`community_ratings()` RPC; returns aggregates only). Discover is still the fictional, labeled *Example* feed — a real community feed needs public sharing and moderation, so it's left for later.
- **Topics and name** are stored in your profile (already synced since v1).
- **Security:** RLS on every table; security-definer helpers live in the non-exposed `private` schema behind security-invoker wrappers; inserts/updates are column-limited; the publishable key is the only key in the page.

## Database changes

Make changes as **new files in `supabase/migrations/`** applied with `apply_migration`. `supabase/schema.sql` is v1-only and drops tables — never run it on the live project.

## Known limits

- Free projects pause after ~1 week of no traffic (one click to resume).
- Anonymous sign-ins: 30/hour per IP. Email/OTP: one request per 60 s per address; codes expire after 1 hour.
- A guest who never saves an email loses access if they clear site data or switch devices.
- Listen reward is still "coming soon" (no payments).

## Tests

`tests/run_all.sh` starts a local Supabase-compatible stack: PostgreSQL 17, the real Supabase Auth (GoTrue) and PostgREST binaries, a small gateway, and **Mailpit** to catch emails. Then it runs:
- `tests/test_rls.py`: 68 SQL-level checks (bridges, reveal rules, chat, isolation, library: owner/partner/outsider/anon, column limits, duplicates, community ratings ≥3 threshold).
- `tests/e2e_two_users.py`: two-phone Playwright run of the v1 flow (create → invite → join → answer → rate → chat, plus a full bridge, a bogus token, and an outsider).
- `tests/e2e_library_email.py`: library migration/add, a friend viewing your library, starting a bridge from an item, save-account by email code (same user id), wrong code, taken email, unknown email, sign-in on a new browser and a second phone with bridges + library + topics syncing.

Hosted smoke test: `python3 tests/serve.py 8081` (no `SB_KEY` → real config), then `BASE=http://127.0.0.1:8081/ REALTIME=1 python3 tests/e2e_two_users.py` (3 guest sign-ups) and `BASE=http://127.0.0.1:8081/ python3 tests/smoke_hosted_v2.py` (2 guest sign-ups, sends no email). Clean up with `tests/cleanup_test_data.sql` (only removes users named `Smoke*`). Don't run the email E2E against the hosted project.
