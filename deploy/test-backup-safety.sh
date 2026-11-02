#!/usr/bin/env bash
set -euo pipefail

# Tests failure handling with a simulated database; no real database is touched.
work="$(mktemp -d /tmp/apex-backup-safety-XXXXXXXX)"
cleanup() {
  rm -f -- "$work/bin/docker" "$work/backups/"* "$work/stopped" "$work/started" "$work/restored" "$work/output" "$work/error"
  rmdir -- "$work/bin" "$work/backups" "$work"
}
trap cleanup EXIT
mkdir -p "$work/bin" "$work/backups"
cat > "$work/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  *'pg_dump'*) if [[ "${TEST_FAIL_DUMP:-0}" == 1 ]]; then printf 'partial'; exit 1; fi; printf 'synthetic-archive' ;;
  *'pg_restore --list'*) [[ "${TEST_INVALID_ARCHIVE:-0}" != 1 ]] && [[ "$(cat)" == 'synthetic-archive' ]] ;;
  *'pg_restore --clean'*) [[ "$*" == *'--single-transaction'* ]] && cat > "$TEST_WORK/restored" ;;
  *'stop api web'*) touch "$TEST_WORK/stopped" ;;
  *'start api web'*) touch "$TEST_WORK/started" ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$work/bin/docker"
export PATH="$work/bin:$PATH" TEST_WORK="$work"
if TEST_FAIL_DUMP=1 bash deploy/backup.sh "$work/backups" > "$work/output" 2> "$work/error"; then
  echo 'Expected dump failure' >&2; exit 1
fi
[[ -z "$(find "$work/backups" -maxdepth 1 -type f -print -quit)" ]]
bash deploy/backup.sh "$work/backups" > "$work/output"
backup=("$work/backups/"*.dump)
[[ ${#backup[@]} == 1 && "$(cat "${backup[0]}")" == 'synthetic-archive' ]]
if TEST_INVALID_ARCHIVE=1 RESTORE_CONFIRM=REPLACE_APEX_DATABASE bash deploy/restore.sh "${backup[0]}" > "$work/output" 2> "$work/error"; then
  echo 'Expected invalid archive failure' >&2; exit 1
fi
[[ ! -e "$work/stopped" ]]
RESTORE_CONFIRM=REPLACE_APEX_DATABASE bash deploy/restore.sh "${backup[0]}" > "$work/output"
[[ "$(cat "$work/restored")" == 'synthetic-archive' && -e "$work/stopped" && -e "$work/started" ]]
echo 'Backup and transactional restore safety checks passed with a simulated database.'
