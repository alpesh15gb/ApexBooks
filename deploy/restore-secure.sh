#!/usr/bin/env bash
set -euo pipefail

# Refuse external or ambiguous targets before creating files or changing data.
python3 "$(dirname -- "${BASH_SOURCE[0]}")/check_backup_target.py"

# Decrypt and validate before stopping the application or changing the database.
backup="${1:-}"
identity="${APEX_RESTORE_IDENTITY_FILE:-}"
if [[ -z "$backup" || ! -f "$backup" || -z "$identity" || ! -f "$identity" ]]; then
  echo 'Usage: APEX_RESTORE_IDENTITY_FILE=/secure/key deploy/restore-secure.sh /path/to/backup.dump.age' >&2
  exit 1
fi
if [[ "${RESTORE_CONFIRM:-}" != 'REPLACE_APEX_DATABASE' ]]; then
  echo 'Set RESTORE_CONFIRM=REPLACE_APEX_DATABASE after reviewing the target and backup' >&2
  exit 1
fi
command -v age >/dev/null || { echo 'Missing required command: age' >&2; exit 1; }
umask 077
working="$(mktemp -d "${APEX_RESTORE_TEMP_DIR:-/tmp}/apex-restore-XXXXXXXX")"
trap 'rm -f -- "$working/backup.dump"; rmdir -- "$working"' EXIT
age -d -i "$identity" "$backup" > "$working/backup.dump"
if [[ ! -s "$working/backup.dump" ]] || ! docker compose exec -T db pg_restore --list < "$working/backup.dump" >/dev/null; then
  echo 'Decrypted backup is not a valid PostgreSQL archive' >&2
  exit 1
fi
RESTORE_CONFIRM=REPLACE_APEX_DATABASE bash deploy/restore.sh "$working/backup.dump"
