#!/usr/bin/env bash
set -euo pipefail

# Refuse external or ambiguous targets before creating files or changing data.
python3 "$(dirname -- "${BASH_SOURCE[0]}")/check_backup_target.py"

# Run from the project root for a reviewed local Compose database only. Restores the entire database.
backup="${1:-}"
if [[ -z "$backup" || ! -f "$backup" ]]; then
  echo "Usage: deploy/restore.sh /path/to/apex-backup.dump" >&2
  exit 1
fi
if [[ "${RESTORE_CONFIRM:-}" != "REPLACE_APEX_DATABASE" ]]; then
  echo "Set RESTORE_CONFIRM=REPLACE_APEX_DATABASE after reviewing the target and backup" >&2
  exit 1
fi
if ! docker compose exec -T db pg_restore --list < "$backup" >/dev/null; then
  echo 'Backup is not a valid PostgreSQL archive' >&2
  exit 1
fi
trap 'docker compose start api web' EXIT
docker compose stop api web
docker compose exec -T db pg_restore --clean --if-exists --no-owner --single-transaction -U apex -d apex < "$backup"
echo "Restore completed from: $backup"
