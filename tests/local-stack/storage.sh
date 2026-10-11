#!/usr/bin/env bash
# Starts the real Supabase Storage API (github.com/supabase/storage, built from source; file backend) on :5000.
# It runs its own migrations (storage schema + roles) on first start, like a hosted project.
# Build once (needs Node >= 24, g++/make):
#   git clone --depth 1 --branch v1.81.0 https://github.com/supabase/storage.git "$STORAGE_SRC"
#   cd "$STORAGE_SRC" && npm ci --ignore-scripts && npm rebuild fs-xattr && node ./build.js && npx resolve-tspaths
# Skipped (with a note) if STORAGE_SRC isn't built — avatar tests then fail with a clear message.
set -euo pipefail
RUN="${RUN:-/tmp/bridge-stack}"; STORAGE_SRC="${STORAGE_SRC:-/workspace/bridge-ops/storage-src}"
NODE24="${NODE24:-$(ls -d /workspace/bridge-mobile/tools/node24/bin 2>/dev/null || dirname "$(command -v node)")}"
SECRET="super-secret-jwt-token-with-at-least-32-characters-long"
[ -f "$STORAGE_SRC/dist/start/server.js" ] || { echo "storage: not built at $STORAGE_SRC (see header of $0) — skipping"; exit 0; }
curl -sf http://127.0.0.1:5000/status >/dev/null 2>&1 && { echo "storage: already up"; exit 0; }
jwt(){ "$NODE24/node" -e 'const c=require("crypto"),s=process.argv[1],b=o=>Buffer.from(JSON.stringify(o)).toString("base64url");const h=b({alg:"HS256",typ:"JWT"}),p=b({iss:"supabase-local",role:process.argv[2],iat:1700000000,exp:2000000000});console.log(h+"."+p+"."+c.createHmac("sha256",s).update(h+"."+p).digest("base64url"))' "$SECRET" "$1"; }
mkdir -p "$RUN/storage-data"
( cd "$STORAGE_SRC" && env -i PATH="$NODE24:/usr/bin:/bin" HOME="$HOME" NODE_ENV=production SERVER_HOST=127.0.0.1 SERVER_PORT=5000 SERVER_ADMIN_PORT=5001 SERVER_REGION=local \
  AUTH_JWT_SECRET="$SECRET" AUTH_JWT_ALGORITHM=HS256 ANON_KEY="$(jwt anon)" SERVICE_KEY="$(jwt service_role)" \
  DATABASE_URL="postgresql://postgres@127.0.0.1:54322/postgres" DB_INSTALL_ROLES=true DB_ANON_ROLE=anon DB_SERVICE_ROLE=service_role \
  DB_AUTHENTICATED_ROLE=authenticated DB_SUPER_USER=postgres DB_ALLOW_MIGRATION_REFRESH=true \
  TENANT_ID=local STORAGE_BACKEND=file STORAGE_FILE_BACKEND_PATH="$RUN/storage-data" STORAGE_S3_BUCKET=local-bucket GLOBAL_S3_BUCKET=local-bucket \
  UPLOAD_FILE_SIZE_LIMIT=52428800 IMAGE_TRANSFORMATION_ENABLED=false PG_QUEUE_ENABLE=false RATE_LIMITER_ENABLED=false \
  OTEL_METRICS_ENABLED=false PROMETHEUS_METRICS_ENABLED=false LOGFLARE_ENABLED=false LOG_LEVEL=warn NODE_OPTIONS=--max-old-space-size=384 \
  nohup node dist/start/server.js > "$RUN/storage.log" 2>&1 & echo $! > "$RUN/storage.pid" )
for i in $(seq 180); do curl -sf http://127.0.0.1:5000/status >/dev/null && { echo "storage: up on :5000"; exit 0; }; sleep 1; done
echo "storage: failed to start, see $RUN/storage.log"; tail -20 "$RUN/storage.log"; exit 1
