#!/usr/bin/env bash
# All processes share one network namespace; no hosted database is used.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
python="${APEX_PYTHON:-python}"
work="$(mktemp -d /tmp/apex-http-e2e-XXXXXXXX)"
api_pid=''; web_pid=''
api_port="${APEX_API_PORT:-18080}"
web_port="${APEX_WEB_PORT:-15173}"
export API_PROXY_TARGET="http://127.0.0.1:$api_port"
cleanup() {
  [[ -z "$api_pid" ]] || kill "$api_pid" 2>/dev/null || true
  [[ -z "$web_pid" ]] || kill "$web_pid" 2>/dev/null || true
  rm -rf -- "$work"
}
trap cleanup EXIT
export DATABASE_URL="sqlite:///$work/isolated.db"
export JWT_SECRET='synthetic-http-e2e-secret-not-for-production'
unset ACCEPTANCE_BASE
(cd "$root/backend" && "$python" migrate.py)
(cd "$root/backend" && exec "$python" -m uvicorn main:app --host 127.0.0.1 --port "$api_port") >"$work/api.log" 2>&1 & api_pid=$!
(cd "$root/frontend" && exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --port "$web_port" --strictPort) >"$work/web.log" 2>&1 & web_pid=$!
ready=0
for _ in $(seq 1 40); do
  if ! kill -0 "$api_pid" 2>/dev/null || ! kill -0 "$web_pid" 2>/dev/null; then
    cat "$work/api.log" "$work/web.log"; exit 1
  fi
  if curl --noproxy '*' --silent --fail http://127.0.0.1:$web_port/api/health >/dev/null; then ready=1; break; fi
  sleep 1
done
if [[ "$ready" != 1 ]]; then cat "$work/api.log" "$work/web.log"; exit 1; fi
APEX_E2E_BASE=http://127.0.0.1:$web_port "$python" "$root/tests/e2e/test_http_workflow.py"
if [[ "${APEX_PERF:-0}" == 1 ]]; then
  APEX_E2E_BASE=http://127.0.0.1:$web_port "$python" "$root/tests/e2e/benchmark_local.py"
fi

if [[ "${APEX_BROWSER:-0}" == 1 ]]; then
  APEX_E2E_BASE=http://127.0.0.1:$web_port "$python" "$root/tests/e2e/browser_workflow.py"
fi
