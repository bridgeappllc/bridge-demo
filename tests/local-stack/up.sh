#!/usr/bin/env bash
# Local Supabase-compatible stack for testing WITHOUT a Supabase account:
#   real PostgreSQL + real Supabase Auth (GoTrue) binary + real PostgREST binary
#   + a tiny Node gateway standing in for Kong (/auth/v1, /rest/v1).
# Not included: Supabase Realtime (the app falls back to polling).
# Needs: postgresql (initdb/pg_ctl/psql), node, gh (for downloads), Linux x86_64.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
RUN="${RUN:-/tmp/bridge-stack}"; BIN="$HERE/bin"; mkdir -p "$RUN" "$BIN"
PGBIN="$(ls -d /usr/lib/postgresql/*/bin | sort -V | tail -1)"; export PATH="$PGBIN:$PATH"
SECRET="super-secret-jwt-token-with-at-least-32-characters-long"
[ -x "$BIN/auth" ] || { gh release download -R supabase/auth v2.197.0 -p 'auth-v2.197.0-x86.tar.gz' -D "$BIN" --clobber && tar xzf "$BIN"/auth-*.tar.gz -C "$BIN"; }
[ -x "$BIN/postgrest" ] || { gh release download -R PostgREST/postgrest v16.4 -p 'postgrest-v16.4-linux-static-x86-64.tar.xz' -D "$BIN" --clobber && tar xJf "$BIN"/postgrest-*.tar.xz -C "$BIN"; }
if [ ! -d "$RUN/pgdata" ]; then
  initdb -D "$RUN/pgdata" -U postgres --auth=trust -E UTF8 >/dev/null
  printf "port=54322\nlisten_addresses='127.0.0.1'\nunix_socket_directories='/tmp'\nwal_level=logical\n" >> "$RUN/pgdata/postgresql.conf"
  pg_ctl -D "$RUN/pgdata" -l "$RUN/pg.log" start >/dev/null; sleep 2
  psql -h 127.0.0.1 -p 54322 -U postgres -q -v ON_ERROR_STOP=1 -f "$HERE/bootstrap.sql" >/dev/null
else pg_ctl -D "$RUN/pgdata" -l "$RUN/pg.log" status >/dev/null || { pg_ctl -D "$RUN/pgdata" -l "$RUN/pg.log" start >/dev/null; sleep 2; }; fi
# Supabase Auth: runs its own migrations (creates auth.users, auth.uid(), ...)
( export GOTRUE_API_HOST=127.0.0.1 PORT=9999 API_EXTERNAL_URL=http://127.0.0.1:54321/auth/v1 GOTRUE_SITE_URL=http://127.0.0.1:8080 \
  GOTRUE_DB_DRIVER=postgres DATABASE_URL="postgres://supabase_auth_admin:authpass@127.0.0.1:54322/postgres?sslmode=disable" \
  GOTRUE_DB_NAMESPACE=auth GOTRUE_DB_MIGRATIONS_PATH="$BIN/migrations" GOTRUE_JWT_SECRET="$SECRET" GOTRUE_JWT_EXP=3600 \
  GOTRUE_JWT_AUD=authenticated GOTRUE_JWT_DEFAULT_GROUP_NAME=authenticated GOTRUE_JWT_ADMIN_ROLES=service_role \
  GOTRUE_EXTERNAL_ANONYMOUS_USERS_ENABLED=true GOTRUE_EXTERNAL_EMAIL_ENABLED=true GOTRUE_MAILER_AUTOCONFIRM=true GOTRUE_RATE_LIMIT_ANONYMOUS_USERS=1000
  nohup "$BIN/auth" > "$RUN/auth.log" 2>&1 & echo $! > "$RUN/auth.pid" )
for i in $(seq 30); do curl -sf http://127.0.0.1:9999/health >/dev/null && break; sleep 1; done
psql -h 127.0.0.1 -p 54322 -U postgres -q -v ON_ERROR_STOP=1 -f "$ROOT/supabase/schema.sql" 2>/dev/null
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
sleep 2; echo "Stack up: API http://127.0.0.1:54321  anon key in $RUN/anon.key"
