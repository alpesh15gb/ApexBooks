#!/usr/bin/env bash
set -euo pipefail

# Uses real age encryption and fake docker/rclone commands; no database is touched.
command -v age >/dev/null
command -v age-keygen >/dev/null
work="$(mktemp -d /tmp/apex-backup-test-XXXXXXXX)"
cleanup() {
  rm -f -- "$work/key" "$work/other-key" "$work/remote/"* "$work/backups/"* "$work/bin/docker" "$work/bin/rclone" "$work/restored" "$work/stopped" "$work/started" "$work/output" "$work/error"
  rmdir -- "$work/remote" "$work/backups" "$work/bin" "$work"
}
trap cleanup EXIT
mkdir -p "$work/bin" "$work/backups" "$work/remote"
cat > "$work/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "$*" in
  'compose config --format json') printf '%s' '{"services":{"db":{"image":"postgres:16-alpine","environment":{"POSTGRES_DB":"apex","POSTGRES_USER":"apex"}},"api":{"environment":{"DATABASE_URL":"postgresql+psycopg://apex:synthetic@db:5432/apex"}}}}' ;;
  'compose exec -T api python -c '*) exit 0 ;;
  *'pg_dump'*) if [[ "${TEST_EMPTY_DUMP:-0}" == 1 ]]; then exit 0; fi; if [[ "${TEST_FAIL_DUMP:-0}" == 1 ]]; then printf 'partial'; exit 1; fi; printf 'synthetic-postgres-archive' ;;
  *'pg_restore --list'*) [[ "$(cat)" == 'synthetic-postgres-archive' ]] ;;
  *'pg_restore --clean'*) [[ "${TEST_FAIL_RESTORE:-0}" != 1 ]] || exit 21; cat > "$TEST_WORK/restored" ;;
  *'stop api web'*) touch "$TEST_WORK/stopped" ;;
  *'start api web'*) touch "$TEST_WORK/started" ;;
  *) exit 1 ;;
esac
EOF
cat > "$work/bin/rclone" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  copyto) [[ "${TEST_FAIL_UPLOAD:-0}" != 1 ]] || exit 1; cp -- "$3" "$TEST_WORK/remote/${4##*/}" ;;
  cat) if [[ "${TEST_CORRUPT_REMOTE:-0}" == 1 ]]; then printf 'corrupt'; else cat -- "$TEST_WORK/remote/${2##*/}"; fi ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$work/bin/docker" "$work/bin/rclone"
export APEX_BACKUP_SCOPE=compose-local
export TEST_WORK="$work" PATH="$work/bin:$PATH"
age-keygen -o "$work/key" 2>/dev/null
age-keygen -o "$work/other-key" 2>/dev/null
export APEX_BACKUP_RECIPIENT="$(age-keygen -y "$work/key")" APEX_BACKUP_REMOTE='test:bucket'
bash deploy/backup-secure.sh "$work/backups" > "$work/output"
backup=("$work/backups/"*.dump.age)
[[ ${#backup[@]} == 1 && -s "${backup[0]}" ]]
[[ "$(stat -c '%a' "${backup[0]}")" == 600 ]]
[[ "$(age -d -i "$work/key" "${backup[0]}")" == 'synthetic-postgres-archive' ]]
cmp -- "${backup[0]}" "$work/remote/${backup[0]##*/}"
if TEST_FAIL_UPLOAD=1 bash deploy/backup-secure.sh "$work/backups" > "$work/output" 2> "$work/error"; then
  echo 'Expected upload failure' >&2; exit 1
fi
backups=("$work/backups/"*.dump.age)
[[ ${#backups[@]} == 2 ]]
if TEST_EMPTY_DUMP=1 bash deploy/backup-secure.sh "$work/backups" > "$work/output" 2> "$work/error"; then
  echo 'Empty database stream was reported as a verified backup' >&2; exit 1
fi
backups=("$work/backups/"*.dump.age)
[[ ${#backups[@]} == 2 ]]
if TEST_FAIL_DUMP=1 bash deploy/backup-secure.sh "$work/backups" > "$work/output" 2> "$work/error"; then
  echo 'Expected dump failure' >&2; exit 1
fi
backups=("$work/backups/"*.dump.age)
[[ ${#backups[@]} == 2 ]]
if TEST_CORRUPT_REMOTE=1 bash deploy/backup-secure.sh "$work/backups" > "$work/output" 2> "$work/error"; then
  echo 'Expected remote verification failure' >&2; exit 1
fi
backups=("$work/backups/"*.dump.age)
[[ ${#backups[@]} == 3 ]]
if RESTORE_CONFIRM=REPLACE_APEX_DATABASE APEX_RESTORE_IDENTITY_FILE="$work/other-key" bash deploy/restore-secure.sh "${backup[0]}" > "$work/output" 2> "$work/error"; then
  echo 'Expected wrong identity to fail' >&2; exit 1
fi
[[ ! -e "$work/stopped" ]]
if TEST_FAIL_RESTORE=1 RESTORE_CONFIRM=REPLACE_APEX_DATABASE APEX_RESTORE_IDENTITY_FILE="$work/key" bash deploy/restore-secure.sh "${backup[0]}" > "$work/output" 2> "$work/error"; then
  echo 'Expected database restore failure' >&2; exit 1
fi
[[ -e "$work/stopped" && ! -e "$work/started" && ! -e "$work/restored" ]]
RESTORE_CONFIRM=REPLACE_APEX_DATABASE APEX_RESTORE_IDENTITY_FILE="$work/key" bash deploy/restore-secure.sh "${backup[0]}" > "$work/output"
[[ "$(cat "$work/restored")" == 'synthetic-postgres-archive' && -e "$work/stopped" && ! -e "$work/started" ]]
echo 'Secure backup and restore flow passed with simulated database and remote storage.'
