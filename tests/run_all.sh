#!/usr/bin/env bash
# Bring up the local stack (incl. Mailpit + Storage, see local-stack/storage.sh), run the DB/API tests and the E2E tests.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; RUN="${RUN:-/tmp/bridge-stack}"
"$HERE/local-stack/up.sh"
python3 "$HERE/test_rls.py"
python3 "$HERE/test_social_rls.py"
python3 "$HERE/test_store_rls.py"
python3 "$HERE/test_filter.py"
python3 "$HERE/test_avatars.py"
SB_KEY="$(cat "$RUN/anon.key")" nohup python3 "$HERE/serve.py" 8080 > "$RUN/serve.log" 2>&1 & echo $! > "$RUN/serve.pid"; sleep 1
python3 "$HERE/e2e_two_users.py"
python3 "$HERE/e2e_library_email.py"
python3 "$HERE/e2e_social.py"
python3 "$HERE/e2e_store.py"
python3 "$HERE/e2e_filter.py"
python3 "$HERE/e2e_avatars.py"
python3 "$HERE/e2e_signout.py"
python3 "$HERE/e2e_header_menu.py"
