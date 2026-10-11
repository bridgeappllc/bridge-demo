# Bridge — setup & status

Live: https://bridgeappllc.github.io/bridge-demo/ (old prototype: `/bridge-demo/demo.html`).
Backend: **Supabase** project `bridge` (Free plan, $0) — ref `gozjxubvvzxkkoxxvldo`, us-west-1.
Frontend: one static `index.html` on GitHub Pages (config block at the top: project URL + publishable key).

## Social (live since Oct 11; preview repo https://bridgeappllc.github.io/bridge-preview/ kept)
- Migration `supabase/migrations/20261011090000_social_profiles_friends.sql` (applied to the hosted project on Oct 11, additive; the live app keeps working).
- **Profiles:** optional unique `@username` (3–20 of a–z, 0–9, _; suggested from your name in Settings), short bio (≤160). Name, @username and bio are visible to signed-in users through `search_people` / `get_profile` RPCs only (the `profiles` table itself stays own-row-only, so topics etc. are never exposed). Profile link: `#u/@username` or `#u/<id>`; it works before sign-up (you land on the profile after entering your name). Old `#lib/<id>` links redirect to the profile.
- **Friends:** `friendships` table (pending/accepted, one row per pair) written only via RPCs: `send_friend_request` (auto-accepts if they already asked you), `respond_friend_request`, `remove_friend` (cancel/decline/unfriend). Friends list (`friends_of`) visible to the user and their friends. Pending requests badge on People and Profile → Friends.
- **Reserved @usernames** (migration `20261011120000_reserved_usernames.sql`): bridge, bridges, bridgeapp, bridgeappllc, thebridge, meetonthebridge, clipclub, admin, administrator, root, system, support, help, helpdesk, official, staff, team, moderator, mod, security, privacy, legal, abuse, contact, info, hello, noreply, no_reply, api, www, app, settings, profile, people, null, undefined — enforced by a CHECK constraint (`private.is_reserved_username`) and reported as unavailable in Settings.
- **Blocks:** `block_user` / `unblock_user`: hides each other in search, profiles and libraries and ends the friendship; existing bridges stay.
- **Library visibility** (Settings → Who can see my library): Everyone (any signed-in user) / **Friends only** (default: friends + people you've been on a bridge with, i.e. the old rule is kept) / Only me. Enforced by RLS via `private.can_view_library`.
- **People** tab: search by name or @username, friend requests, "People you've bridged with" suggestions, share your profile link.
- **Start a bridge with a friend:** from a friend's profile or one of their library items; the friend is prefilled and added to the bridge directly (`add_friend_to_bridge`, accepted friends only), and the invite link still works.
- **Discover** now shows real recent items from friends' libraries (category filter); the fictional example feed is gone.
- Tests: `tests/test_social_rls.py` (79 DB checks), `tests/e2e_social.py` (3 phones, 25 checks).

## Status (Oct 8, 2026)

- ✅ v1 (Oct 8): real bridges — invite link, guest join with a name, 3 answers with reveal, stored chat with realtime, Your Bridges.
- ✅ v3 (Oct 9): **rating step removed.** Flow is Invite → Answer → Talk; your chat opens as soon as you submit your answers (migration `remove_rating_step`, file `supabase/migrations/20261009090000_remove_rating_step.sql`). Old ratings are kept in the database but are no longer readable or used.
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
- **Bridge flow:** Invite → Answer 3 questions → Talk. You see your friend's answers only after submitting yours, and your chat opens as soon as you've submitted your answers (your friend joins the chat once they've answered). Discover is still the fictional, labeled *Example* feed — a real community feed is for later.
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
- `tests/test_rls.py`: 69 SQL-level checks (bridges, reveal rules, chat opens after answering, isolation, library: owner/partner/outsider/anon, column limits, duplicates, ratings retired).
- `tests/e2e_two_users.py`: two-phone Playwright run (create → invite → join → answer → chat both ways, plus a full bridge, a bogus token, an outsider, and a sweep for leftover rating wording).
- `tests/test_upgrade_v3.py`: upgrade check — builds a bridge stuck at the old Rate step with the pre-v3 app on a v2 database, applies the v3 migration (row counts must not change), then confirms the new app opens that bridge in Talk and chat works both ways. Run it on a stack started with `MIGRATE_UNTIL=20261008160000 tests/local-stack/up.sh` (see the docstring).
- `tests/e2e_library_email.py`: library migration/add, a friend viewing your library, starting a bridge from an item, save-account by email code (same user id), wrong code, taken email, unknown email, sign-in on a new browser and a second phone with bridges + library + topics syncing.

Hosted smoke test: `python3 tests/serve.py 8081` (no `SB_KEY` → real config), then `BASE=http://127.0.0.1:8081/ REALTIME=1 python3 tests/e2e_two_users.py` (3 guest sign-ups) and `BASE=http://127.0.0.1:8081/ python3 tests/smoke_hosted_v2.py` (2 guest sign-ups, sends no email). Clean up with `tests/cleanup_test_data.sql` (only removes users named `Smoke*`). Don't run the email E2E against the hosted project.

## Store requirements (account deletion, reports, legal pages)
- Migration `20261011150000_account_deletion_and_reports.sql`: `delete_my_account()` RPC (Settings → Delete account), `report_content()` RPC + `public.reports`
  (no client access), moderation view `private.reports_review`, shared bridges survive a deleted partner (`bridges.partner_left_at`).
- How to review reports: see `docs/MODERATION.md`.
- `privacy.html`, `terms.html`, `support.html` are **drafts** for Bridge LLC review (not legal advice). They're linked from welcome, sign-up and Settings.
- Tests: `tests/test_store_rls.py` (DB rules) and `tests/e2e_store.py` (UI); both are in `tests/run_all.sh`.
