#!/usr/bin/env bash
# Reproducible, synthetic-only web/API release checks. Never targets hosted books.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -n "${ACCEPTANCE_BASE:-}" ]]; then
  echo 'Refusing ACCEPTANCE_BASE: this check is isolated and must not write to a hosted API.' >&2
  exit 2
fi
PYTHON="${PYTHON:-python}"
"$PYTHON" -m unittest discover -s backend -p 'test_*.py' -v
(cd frontend && node --test tests/*.test.mjs && npm run lint && npm run build)
APEX_PYTHON="$PYTHON" bash tests/e2e/run-local.sh
contract_dir="$(mktemp -d /tmp/apex-contract-XXXXXXXX)"
trap 'rm -rf -- "$contract_dir"' EXIT
# Import with an in-memory engine and no external credentials or migrations.
PYTHONPATH=backend DATABASE_URL=sqlite:// JWT_SECRET=synthetic-contract-check-secret-32chars \
  "$PYTHON" -c 'import json; from main import app; print(json.dumps(app.openapi()))' > "$contract_dir/openapi.json"
"$PYTHON" native/tools/check_api_routes.py --contract "$contract_dir/openapi.json" --output "$contract_dir/routes.json"
bash deploy/test-backup-safety.sh
if command -v age >/dev/null && command -v age-keygen >/dev/null; then
  bash deploy/test-secure-backup.sh
else
  echo 'NOT RUN: encrypted backup safety tests require age and age-keygen.' >&2
fi
