#!/usr/bin/env bash
# Bring up the local stack, run the SQL/RLS tests and the two-browser E2E test.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; RUN="${RUN:-/tmp/bridge-stack}"
"$HERE/local-stack/up.sh"
python3 "$HERE/test_rls.py"
SB_KEY="$(cat "$RUN/anon.key")" nohup python3 "$HERE/serve.py" 8080 > "$RUN/serve.log" 2>&1 & echo $! > "$RUN/serve.pid"; sleep 1
python3 "$HERE/e2e_two_users.py"
