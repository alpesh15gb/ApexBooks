#!/usr/bin/env bash
set -euo pipefail

# Encrypt before writing to disk and verify the uploaded ciphertext byte for byte.
# Run from the project root. The backup contains all companies and tenants.
backup_dir="${1:-/var/backups/apex-books}"
recipient="${APEX_BACKUP_RECIPIENT:?Set APEX_BACKUP_RECIPIENT to an age public recipient}"
remote="${APEX_BACKUP_REMOTE:?Set APEX_BACKUP_REMOTE to an rclone remote path}"
if [[ ! "$remote" =~ ^[[:alnum:]_.-]+: ]]; then
  echo 'APEX_BACKUP_REMOTE must be an rclone remote such as backup:bucket/path' >&2
  exit 1
fi
for command in docker age rclone sha256sum; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 1; }
done
umask 077
mkdir -p -- "$backup_dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
temporary="$(mktemp "$backup_dir/.apex-$stamp-XXXXXXXX")"
trap 'rm -f -- "$temporary"' EXIT
temporary_name="${temporary##*/}"
target="${backup_dir%/}/${temporary_name#.}.dump.age"
if ! docker compose exec -T db pg_dump -U apex -d apex -Fc | age -r "$recipient" > "$temporary"; then
  echo 'Backup failed before encryption completed' >&2
  exit 1
fi
if [[ ! -s "$temporary" ]]; then echo 'Backup was empty' >&2; exit 1; fi
if ! ln -T -- "$temporary" "$target"; then
  echo 'Could not create a unique backup filename' >&2
  exit 1
fi
rm -f -- "$temporary"
remote_target="${remote%/}/${target##*/}"
if ! rclone copyto --immutable "$target" "$remote_target"; then
  echo "Offsite upload failed; encrypted local backup retained: $target" >&2
  exit 1
fi
local_hash="$(sha256sum "$target" | cut -d ' ' -f1)"
if ! remote_hash="$(rclone cat "$remote_target" | sha256sum | cut -d ' ' -f1)" || [[ "$local_hash" != "$remote_hash" ]]; then
  echo "Offsite verification failed; encrypted local backup retained: $target" >&2
  exit 1
fi
echo "Encrypted backup uploaded and verified: $target"
