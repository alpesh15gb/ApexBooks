# Encrypted offsite database backups

The secure backup contains the entire PostgreSQL database, including every company and tenant. The script streams `pg_dump` through `age` before writing to disk, uploads the encrypted file to an rclone remote, then reads the remote file back and compares its SHA-256 hash. A failed upload or verification returns a nonzero status and keeps the encrypted local file for recovery.

## Supported target and required preflight

These four shell helpers support **only the root `docker-compose.yml` local PostgreSQL service** (`db`, database/user `apex`). They are **not a backup procedure for the separate `deploy/vps` external/hosted PostgreSQL deployment or a Vercel-linked database**. Do not use them to assert that a hosted database is protected.

Set `APEX_BACKUP_SCOPE=compose-local` only after reviewing the target. Before creating/decrypting any backup or stopping services, the helpers require Python 3, resolve Compose configuration privately, reject external/ambiguous database targets, and verify that the running API is configured for the same local database. Configuration and credentials are never printed by this guard. Both backup service units read the explicit `/etc/apex-books/backup.env` file; exporting a variable in an interactive shell does not configure a systemd timer. The local unencrypted service also requires that file, containing `APEX_BACKUP_SCOPE=compose-local` only after target review. Neither service automatically opts in; a missing file or missing scope fails closed. Updating these source files does not install, reload or activate a service.

A stopped/unavailable API fails closed: perform an operator-reviewed recovery procedure instead of bypassing the check. This guard checks configuration identity, not server contents, backup restorability, or protection against a malicious host administrator.

For hosted PostgreSQL, establish a provider-specific snapshot/PITR and full-database export/recovery plan, with tested credentials, retention, recovery-point/time objectives and an isolated restore drill. No provider backup, schedule or production recovery has been configured by these source changes.

A company ZIP/JSON export is **not** a whole-database backup: it restores a new company and does not restore authentication, memberships or all operational metadata. Before a release, verify a full-database recovery point and rehearse migrations on an isolated clone. Coordinate every application sharing that database. Reverting containers or proxy configuration does not revert schema or data; additive migrations can still have destructive downgrades. Do not drop new receipt/transfer tables or labels as a routine rollback. Once new writes occur, agree how to retain/reconcile those writes before any full-database restore.

## Configure on a local-Compose host

1. Install `age` and `rclone` from trusted sources on the VPS. Configure an rclone remote for an offsite storage destination; protect its credentials and restrict access to the backup bucket.
2. Generate an age identity on a separate trusted recovery machine using `age-keygen`. Store the private identity securely off the VPS, with a second protected recovery copy. Obtain its public recipient with `age-keygen -y /path/to/identity`. Losing the identity makes the encrypted backups unrecoverable.
3. Create `/etc/apex-books/backup.env`, owned by root and readable only by root (`chmod 600`). Put the public recipient and rclone destination in it, for example:

   ```ini
   APEX_BACKUP_SCOPE=compose-local
   APEX_BACKUP_RECIPIENT=age1REPLACE_WITH_PUBLIC_RECIPIENT
   APEX_BACKUP_REMOTE=backup:bucket/apex-books
   ```

   Do not put the private age identity in this file. The systemd service runs as root, so configure rclone for that account or set `RCLONE_CONFIG` to a protected configuration file in `backup.env`.
4. From `/opt/apex-books`, test a backup using those environment values:

   ```bash
   sudo bash -c 'set -a; . /etc/apex-books/backup.env; set +a; bash deploy/backup-secure.sh /var/backups/apex-books'
   ```

   Confirm the command succeeds, the encrypted local file exists, and the remote contains the matching file. A failed offsite upload leaves the encrypted local file in place and reports failure.
5. Install `apex-secure-backup.service` and `apex-secure-backup.timer` in `/etc/systemd/system`, run `sudo systemctl daemon-reload`, then `sudo systemctl enable --now apex-secure-backup.timer`. If the older `apex-backup.timer` is enabled, disable it after the secure timer is verified to avoid continuing unencrypted local backups.
6. Check `systemctl status apex-secure-backup.timer` and `journalctl -u apex-secure-backup.service` regularly. Configure an external alert for failed runs and storage capacity. Files are not automatically deleted; set and test retention with the storage provider according to the business's recovery needs.

## Restore and rehearse

Test restores on an isolated host with a compatible application and database version. The following command replaces the entire target database. Transfer the encrypted backup and the private identity to the recovery host through an approved secure channel; remove the identity from the host after use if it is not normally stored there.

```bash
APEX_BACKUP_SCOPE=compose-local \
RESTORE_CONFIRM=REPLACE_APEX_DATABASE \
APEX_RESTORE_IDENTITY_FILE=/secure/recovery-identity.txt \
bash deploy/restore-secure.sh /path/to/apex-backup.dump.age
```

The script decrypts to a private temporary directory, verifies the PostgreSQL archive can be listed, then calls `restore.sh`. That script stops the application and restores inside one PostgreSQL transaction. It never automatically restarts `api` or `web`, on success or failure. If stopping fails, no restore is attempted. After a successful restore, keep every writer paused while checking restored balances, attachment access, schema/application compatibility and readiness; resume only through the reviewed operator procedure. A failed restore also leaves these services stopped for investigation. External writers are not stopped by this helper. The temporary plaintext is removed on normal exit; a forced kill or machine crash can leave it behind. Set `APEX_RESTORE_TEMP_DIR` to a suitably protected filesystem with enough free space, and check it after an interrupted restore.

Review the recovered companies, balances and a sample document. Record the recovery time and repeat the drill periodically. Backups created by the older `backup.sh` are unencrypted and need separate handling.

## Script test

`bash deploy/test-secure-backup.sh` uses real age encryption with simulated database and remote-storage commands. It checks successful encryption/restore, upload failure, corrupted remote content and a wrong recovery identity. It does not replace a PostgreSQL restore drill or verify a real offsite provider.

`python3 -m unittest discover -s deploy -p test_backup_target.py` tests fail-closed target selection with mocked Docker and synthetic configuration. `bash deploy/test-backup-safety.sh` tests dump/restore failure handling with simulated commands. These checks do not access a live database or validate a real deployment.

The encrypted backup pipeline rejects an empty database output stream before encryption, without writing plaintext to disk. Ciphertext size or upload checksum alone cannot establish that a usable database dump was produced. This guard checks nonempty input, not archive/schema validity; isolated restore verification is still required.
