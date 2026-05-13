#!/usr/bin/env bash
set -euo pipefail
BASE=${BASE:-http://localhost:8000}
echo "Health:" && curl -s "$BASE/health" && echo
