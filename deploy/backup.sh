#!/usr/bin/env bash
set -euo pipefail

# Refuse external or ambiguous targets before creating files or changing data.
python3 "$(dirname -- "${BASH_SOURCE[0]}")/check_backup_target.py"

# Run from the project root for a reviewed local Compose database only. The dump contains every tenant.
backup_dir="${1:-./backups}"
umask 077
mkdir -p -- "$backup_dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$backup_dir/apex-$stamp.dump"
temporary="$(mktemp "$backup_dir/.apex-$stamp-XXXXXXXX")"
trap 'rm -f -- "$temporary"' EXIT
if ! docker compose exec -T db pg_dump -U apex -d apex -Fc > "$temporary"; then
  echo 'Database backup failed' >&2
  exit 1
fi
if [[ ! -s "$temporary" ]]; then
  echo "Backup failed or was empty" >&2
  exit 1
fi
if ! ln -T -- "$temporary" "$target"; then
  echo "Backup already exists or cannot be created: $target" >&2
  exit 1
fi
rm -f -- "$temporary"
echo "Backup created: $target"
