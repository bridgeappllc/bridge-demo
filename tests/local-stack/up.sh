#!/usr/bin/env bash
# Local Supabase-compatible stack for testing WITHOUT a Supabase account:
#   real PostgreSQL + real Supabase Auth (GoTrue) binary + real PostgREST binary
#   + a tiny Node gateway standing in for Kong (/auth/v1, /rest/v1).
#   + Mailpit (mail catcher: SMTP :1025, UI/API http://127.0.0.1:8025) so email OTP flows can be tested.
#   + the real Supabase Storage API (file backend) via storage.sh, if built (/storage/v1).
# Not included: Supabase Realtime (the app falls back to polling).
# Needs: postgresql (initdb/pg_ctl/psql), node, gh (for downloads), Linux x86_64.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
RUN="${RUN:-/tmp/bridge-stack}"; BIN="$HERE/bin"; mkdir -p "$RUN" "$BIN"
PGBIN="$(ls -d /usr/lib/postgresql/*/bin | sort -V | tail -1)"; export PATH="$PGBIN:$PATH"
SECRET="super-secret-jwt-token-with-at-least-32-characters-long"
[ -x "$BIN/auth" ] || { gh release download -R supabase/auth v2.197.0 -p 'auth-v2.197.0-x86.tar.gz' -D "$BIN" --clobber && tar xzf "$BIN"/auth-*.tar.gz -C "$BIN"; }
[ -x "$BIN/mailpit" ] || { gh release download -R axllent/mailpit v1.31.4 -p 'mailpit-linux-amd64.tar.gz' -D "$BIN" --clobber && tar xzf "$BIN"/mailpit-linux-amd64.tar.gz -C "$BIN" mailpit; }
[ -x "$BIN/postgrest" ] || { gh release download -R PostgREST/postgrest v16.4 -p 'postgrest-v16.4-linux-static-x86-64.tar.xz' -D "$BIN" --clobber && tar xJf "$BIN"/postgrest-*.tar.xz -C "$BIN"; }
if [ ! -d "$RUN/pgdata" ]; then
  initdb -D "$RUN/pgdata" -U postgres --auth=trust -E UTF8 >/dev/null
  printf "port=54322\nlisten_addresses='127.0.0.1'\nunix_socket_directories='/tmp'\nwal_level=logical\n" >> "$RUN/pgdata/postgresql.conf"
  pg_ctl -D "$RUN/pgdata" -l "$RUN/pg.log" start >/dev/null; sleep 2
  psql -h 127.0.0.1 -p 54322 -U postgres -q -v ON_ERROR_STOP=1 -f "$HERE/bootstrap.sql" >/dev/null
else pg_ctl -D "$RUN/pgdata" -l "$RUN/pg.log" status >/dev/null || { pg_ctl -D "$RUN/pgdata" -l "$RUN/pg.log" start >/dev/null; sleep 2; }; fi
nohup "$BIN/mailpit" --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025 --smtp-auth-accept-any --smtp-auth-allow-insecure > "$RUN/mailpit.log" 2>&1 & echo $! > "$RUN/mailpit.pid"
TPL="${TPL_BASE:-http://127.0.0.1:8080/supabase/email-templates}"   # served by tests/serve.py
# Supabase Auth: runs its own migrations (creates auth.users, auth.uid(), ...)
( export GOTRUE_API_HOST=127.0.0.1 PORT=9999 API_EXTERNAL_URL=http://127.0.0.1:54321/auth/v1 GOTRUE_SITE_URL=http://127.0.0.1:8080 \
  GOTRUE_DB_DRIVER=postgres DATABASE_URL="postgres://supabase_auth_admin:authpass@127.0.0.1:54322/postgres?sslmode=disable" \
  GOTRUE_DB_NAMESPACE=auth GOTRUE_DB_MIGRATIONS_PATH="$BIN/migrations" GOTRUE_JWT_SECRET="$SECRET" GOTRUE_JWT_EXP=3600 \
  GOTRUE_JWT_AUD=authenticated GOTRUE_JWT_DEFAULT_GROUP_NAME=authenticated GOTRUE_JWT_ADMIN_ROLES=service_role \
  GOTRUE_EXTERNAL_ANONYMOUS_USERS_ENABLED=true GOTRUE_EXTERNAL_EMAIL_ENABLED=true GOTRUE_MAILER_AUTOCONFIRM=false GOTRUE_RATE_LIMIT_ANONYMOUS_USERS=1000 \
  GOTRUE_SMTP_HOST=127.0.0.1 GOTRUE_SMTP_PORT=1025 GOTRUE_SMTP_USER=x GOTRUE_SMTP_PASS=x GOTRUE_SMTP_ADMIN_EMAIL=noreply@bridge.local GOTRUE_SMTP_SENDER_NAME=Bridge \
  GOTRUE_SMTP_MAX_FREQUENCY=1s GOTRUE_RATE_LIMIT_EMAIL_SENT=1000 GOTRUE_URI_ALLOW_LIST="http://127.0.0.1:8080/**" \
  GOTRUE_MAILER_TEMPLATES_MAGIC_LINK="$TPL/magic_link.html" GOTRUE_MAILER_TEMPLATES_EMAIL_CHANGE="$TPL/email_change.html" \
  GOTRUE_MAILER_SUBJECTS_MAGIC_LINK="{{ .Token }} is your Pod Club sign-in code" GOTRUE_MAILER_SUBJECTS_EMAIL_CHANGE="{{ .Token }} is your Pod Club confirmation code"
  nohup "$BIN/auth" > "$RUN/auth.log" 2>&1 & echo $! > "$RUN/auth.pid" )
for i in $(seq 30); do curl -sf http://127.0.0.1:9999/health >/dev/null && break; sleep 1; done
# Supabase Storage (creates the storage schema, like a hosted project) — before our migrations, which add the avatars bucket.
"$HERE/storage.sh"
# Apply the same migration files, in order, that were applied to the hosted project (once per fresh DB).
if [ ! -f "$RUN/migrated" ]; then
  # MIGRATE_UNTIL=<timestamp> stops after that migration (used by the upgrade test)
  for m in "$ROOT"/supabase/migrations/*.sql; do if [ -n "${MIGRATE_UNTIL:-}" ] && [[ "$(basename "$m")" > "${MIGRATE_UNTIL}~" ]]; then continue; fi; psql -h 127.0.0.1 -p 54322 -U postgres -q -v ON_ERROR_STOP=1 -f "$m" >/dev/null; done; [ -z "${MIGRATE_UNTIL:-}" ] && for f in "$ROOT"/supabase/seed/*.sql; do psql -h 127.0.0.1 -p 54322 -U postgres -q -v ON_ERROR_STOP=1 -f "$f" >/dev/null; done; touch "$RUN/migrated"
fi
cat > "$RUN/postgrest.conf" <<CONF
db-uri = "postgres://authenticator:authpass@127.0.0.1:54322/postgres"
db-schemas = "public"
db-anon-role = "anon"
jwt-secret = "$SECRET"
server-host = "127.0.0.1"
server-port = 3000
CONF
nohup "$BIN/postgrest" "$RUN/postgrest.conf" > "$RUN/postgrest.log" 2>&1 & echo $! > "$RUN/postgrest.pid"
nohup node "$HERE/gateway.js" > "$RUN/gateway.log" 2>&1 & echo $! > "$RUN/gateway.pid"
node -e 'const c=require("crypto"),s=process.argv[1],b=o=>Buffer.from(JSON.stringify(o)).toString("base64url");const h=b({alg:"HS256",typ:"JWT"}),p=b({iss:"supabase-local",role:"anon",iat:1700000000,exp:2000000000});console.log(h+"."+p+"."+c.createHmac("sha256",s).update(h+"."+p).digest("base64url"))' "$SECRET" > "$RUN/anon.key"
node -e 'const c=require("crypto"),s=process.argv[1],b=o=>Buffer.from(JSON.stringify(o)).toString("base64url");const h=b({alg:"HS256",typ:"JWT"}),p=b({iss:"supabase-local",role:"service_role",iat:1700000000,exp:2000000000});console.log(h+"."+p+"."+c.createHmac("sha256",s).update(h+"."+p).digest("base64url"))' "$SECRET" > "$RUN/service.key"
# Edge Functions (deno) + a mock Resend API. Local only: the real Resend key is never passed (env -i), mail goes to the mock.
nohup node "$HERE/resend-mock.js" > "$RUN/resend.log" 2>&1 & echo $! > "$RUN/resend.pid"
DENO="${DENO:-$(command -v deno || echo /workspace/tools/deno)}"
if [ -x "$DENO" ]; then
  env -i PATH=/usr/bin:/bin HOME="$HOME" SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_ANON_KEY="$(cat "$RUN/anon.key")" SUPABASE_SERVICE_ROLE_KEY="$(cat "$RUN/service.key")" \
    RESEND_API_KEY=re_local_mock RESEND_API_URL=http://127.0.0.1:54330/emails REMIND_APPS=http://127.0.0.1:8080/ DENO_SERVE_ADDRESS=tcp:127.0.0.1:54329 \
    nohup "$DENO" run --allow-net --allow-env "$HERE/../../supabase/functions/remind/index.ts" > "$RUN/functions.log" 2>&1 & echo $! > "$RUN/functions.pid"
  for i in $(seq 30); do curl -s -o /dev/null -X OPTIONS http://127.0.0.1:54329/ && break; sleep 0.5; done
  env -i PATH=/usr/bin:/bin HOME="$HOME" SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_ANON_KEY="$(cat "$RUN/anon.key")" LINK_PREVIEW_ALLOW_LOCAL=1 DENO_SERVE_ADDRESS=tcp:127.0.0.1:54331 \
    nohup "$DENO" run --allow-net --allow-env "$HERE/../../supabase/functions/link-preview/index.ts" > "$RUN/linkpreview.log" 2>&1 & echo $! > "$RUN/linkpreview.pid"
  for i in $(seq 30); do curl -s -o /dev/null -X OPTIONS http://127.0.0.1:54331/ && break; sleep 0.5; done
  # Tips: Stripe mock (no real key, no network) + the three tips-* functions.
  nohup node "$HERE/stripe-mock.js" > "$RUN/stripemock.log" 2>&1 & echo $! > "$RUN/stripemock.pid"
  for fn in connect:54334 checkout:54335 webhook:54336; do name="tips-${fn%%:*}"; port="${fn##*:}"
    env -i PATH=/usr/bin:/bin HOME="$HOME" SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_ANON_KEY="$(cat "$RUN/anon.key")" SUPABASE_SERVICE_ROLE_KEY="$(cat "$RUN/service.key")" \
      STRIPE_SECRET_KEY=sk_test_local_mock STRIPE_API_URL=http://127.0.0.1:54333 STRIPE_WEBHOOK_SECRET=whsec_local_mock TIPS_APPS=http://127.0.0.1:8080/ DENO_SERVE_ADDRESS=tcp:127.0.0.1:$port \
      nohup "$DENO" run --allow-net --allow-env "$HERE/../../supabase/functions/$name/index.ts" > "$RUN/$name.log" 2>&1 & echo $! > "$RUN/$name.pid"
    for i in $(seq 30); do curl -s -o /dev/null -X OPTIONS http://127.0.0.1:$port/ && break; sleep 0.5; done; done
  # Tips v2 (earn first): tips2-* functions, sandbox-style secrets pointing at the same mock.
  for fn in connect:54337 checkout:54338 webhook:54339 payout:54340; do name="tips2-${fn%%:*}"; port="${fn##*:}"
    env -i PATH=/usr/bin:/bin HOME="$HOME" SUPABASE_URL=http://127.0.0.1:54321 SUPABASE_ANON_KEY="$(cat "$RUN/anon.key")" SUPABASE_SERVICE_ROLE_KEY="$(cat "$RUN/service.key")" \
      STRIPE_SECRET_KEY_SANDBOX=sk_test_local_mock STRIPE_API_URL=http://127.0.0.1:54333 STRIPE_WEBHOOK_SECRET_SANDBOX=whsec_local_mock TIPS2_APPS=http://127.0.0.1:8080/ TIPS_USD_ONLY_APPS=http://127.0.0.1:8080/ TIPS_PREFILL_APPS=http://127.0.0.1:8080/ TIPS2_CRON_SECRET=cron_local_mock DENO_SERVE_ADDRESS=tcp:127.0.0.1:$port \
      nohup "$DENO" run --allow-net --allow-env --allow-read "$HERE/../../supabase/functions/$name/index.ts" > "$RUN/$name.log" 2>&1 & echo $! > "$RUN/$name.pid"
    for i in $(seq 30); do curl -s -o /dev/null -X POST http://127.0.0.1:$port/ && break; sleep 0.5; done; done
else echo "functions: deno not found — skipping"; fi
sleep 2; echo "Stack up: API http://127.0.0.1:54321  anon key in $RUN/anon.key"
