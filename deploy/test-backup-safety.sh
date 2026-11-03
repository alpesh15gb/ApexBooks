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
  'compose config --format json') printf '%s' '{"services":{"db":{"image":"postgres:16-alpine","environment":{"POSTGRES_DB":"apex","POSTGRES_USER":"apex"}},"api":{"environment":{"DATABASE_URL":"postgresql+psycopg://apex:synthetic@db:5432/apex"}}}}' ;;
  'compose exec -T api python -c '*) exit 0 ;;
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
# Every entry point must reject an unreviewed target before touching Docker,
# creating backup directories, decrypting data or requiring real credentials.
for script in backup backup-secure restore restore-secure; do
  if APEX_BACKUP_SCOPE=unreviewed bash "deploy/$script.sh" "$work/backups/not-created" > "$work/output" 2> "$work/error"; then
    echo "Expected target refusal: $script" >&2; exit 1
  fi
  grep -q 'APEX_BACKUP_SCOPE=compose-local' "$work/error"
  [[ ! -e "$work/backups/not-created" && ! -e "$work/stopped" && ! -e "$work/restored" ]]
done
export APEX_BACKUP_SCOPE=compose-local
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
