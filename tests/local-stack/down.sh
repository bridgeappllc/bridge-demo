#!/usr/bin/env bash
RUN="${RUN:-/tmp/bridge-stack}"; PGBIN="$(ls -d /usr/lib/postgresql/*/bin | sort -V | tail -1)"
for s in auth postgrest gateway serve; do [ -f "$RUN/$s.pid" ] && kill "$(cat "$RUN/$s.pid")" 2>/dev/null; rm -f "$RUN/$s.pid"; done
"$PGBIN/pg_ctl" -D "$RUN/pgdata" stop -m fast >/dev/null 2>&1; [ "${1:-}" = "--wipe" ] && rm -rf "$RUN"; echo "Stack down"
