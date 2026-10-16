#!/usr/bin/env bash
RUN="${RUN:-/tmp/bridge-stack}"; PGBIN="$(ls -d /usr/lib/postgresql/*/bin | sort -V | tail -1)"
for s in auth postgrest gateway serve mailpit storage resend functions linkpreview stripemock tips-connect tips-checkout tips-webhook; do [ -f "$RUN/$s.pid" ] && kill "$(cat "$RUN/$s.pid")" 2>/dev/null; rm -f "$RUN/$s.pid"; done
# Storage API: also stop it if its pid file is missing (only the process on :5000 running from our storage build)
STORAGE_SRC="${STORAGE_SRC:-/workspace/bridge-ops/storage-src}"
for pid in $(ss -ltnp 2>/dev/null | awk '$4=="127.0.0.1:5000"' | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u); do
  [ "$(readlink -f /proc/$pid/cwd 2>/dev/null)" = "$(readlink -f "$STORAGE_SRC")" ] && kill "$pid" 2>/dev/null; done
"$PGBIN/pg_ctl" -D "$RUN/pgdata" stop -m fast >/dev/null 2>&1; [ "${1:-}" = "--wipe" ] && rm -rf "$RUN"; echo "Stack down"
