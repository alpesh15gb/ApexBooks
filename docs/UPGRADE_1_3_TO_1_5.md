# 1.3 → 1.5 rollout and recovery prerequisites

This is an operator checklist, not an executed deployment, a production backup, or authorization to change live infrastructure. The draft branch and unsigned CI artifacts do not update an installed application.

## Establish the actual target first

Public HTTPS checks observed version **1.3.0**, readiness success and no capabilities endpoint/build revision on the documented production origins and inspected Vercel preview. A version string does not identify a commit or schema. Database environment values were not read; whether these origins share a database is **unknown**.

Before any migration or cutover, record privately:

- Intended frontend/API origins, provider/project/environment, exact deployed source where recoverable, and current Alembic revision/schema.
- Every API, background worker, preview and installed client that can write to the target database. Stop or isolate incompatible writers during the coordinated upgrade; changing one web origin alone is insufficient.
- Approved immutable 1.5 source revision, built image IDs/artifact hashes and matching API/web/native build metadata. Missing metadata must stay `unknown`, not be guessed.
- Explicit strong JWT configuration, correct existing accounting/commerce encryption identity, HTTPS OCR endpoint and required nonsecret feature configuration. Do not print environment files, use credentials in command arguments or regenerate encryption keys as an incidental upgrade step.

The 1.5 native Release API origin is `https://api.apexbooks.in`. A Vercel-preview-only rollout does not exercise that native destination. Capability negotiation fails closed for optional new features when connected to an older API; it is not a server upgrade mechanism.

## Schema and migration gates

The known repository baseline is `1e8d981149e8a4dce597ec49933b33887bcf00d6`, whose migration head is `e674ab031c58`. The 1.5 chain adds:

| Revision | Change | Recovery warning |
| --- | --- | --- |
| `f785bc142d69` | Optional book label, separate from legal company name | Downgrade drops chosen labels |
| `g896cd253e70` | Retained immutable receipt bytes, tenant/record constraints and write keys | Downgrade discards retained evidence; archived evidence is still evidence |
| `h907ef475a92` | Durable bounded backup jobs/chunks and storage reservations | Downgrade discards transfer and canonical recovery metadata |

These are additive forward migrations, not permission to skip a database backup or assume old code can safely keep writing. Use the standard versioned migration runner only after verifying the actual target revision and rehearsing on an isolated clone. An unexpected or unversioned schema must fail closed for manual review; do not stamp it to head to bypass differences. Current readiness intentionally refuses a database that has not reached the required schema.

### Completed synthetic baseline rehearsal

`python tests/upgrade/rehearse_legacy.py` archives the exact original commit above and runs baseline/current code in separate subprocesses against newly created temporary SQLite databases. It does not use an inherited database URL or a hosted target. It passed locally with:

- Readiness **503 before migration → 200 after migration**, baseline `e674ab031c58` → current `h907ef475a92` through the standard Alembic runner.
- Exact preservation of all original columns/rows across **33 tables**, including 14 records, 11 journals/28 lines, five stock movements and one single/three split payment allocations. Fixture data includes openings, a purchase bill, invoices, partial customer/supplier payments, a linked credit note and expense.
- Six canonical reports unchanged: financial, stock, parties, ageing, buyer statement and supplier statement. Only the new explicitly-null statement `converted_to` metadata is normalized; financial values are compared exactly.
- A second migration run leaves the schema/old rows unchanged. An existing session token and old-client payload omitting new fields still support the exercised core read/draft-write paths.
- A receipt created **after** upgrade survives complete ZIP restore with exact bytes, financial-report equality and same-company commit replay. This is not pre-upgrade attachment preservation.
- A pre-upgrade SQLite physical backup reopens under the original application with identical old rows/reports, without running a destructive downgrade.

The synthetic CI job fetches only the pinned baseline commit when it is not already present, then runs this rehearsal. This does not prove the live database matches that baseline, exercise PostgreSQL migration locks/production row counts, or replace an actual provider-clone upgrade/recovery drill. Some tables have no rows in this representative fixture; general newest-schema regression and concurrency suites remain separate evidence. Ordinary unit tests that create only the newest schema are not upgrade evidence.

## Recovery before execution

1. Establish a verified full-database backup or provider snapshot/PITR, retention and recovery-point/time objectives. Rehearse restoring that recovery point into an isolated target and verify tenant/authentication state as well as financial reports.
2. Inventory retained files, receipt storage and operational staging capacity. The old 1.3 schema has no new retained-receipt tables; postupgrade receipt coverage must not be described as preservation of nonexistent old evidence.
3. Agree a maintenance/write-freeze window or a tested procedure for retaining and reconciling post-cutover writes. Reverting to a pre-upgrade database can lose valid new transactions.
4. Keep approved old application artifacts/configuration and proxy routing snapshots. A proxy/container rollback **does not** undo database changes. Do not automatically run the destructive downgrades above; prefer a reviewed forward fix or isolated full recovery with a write-reconciliation plan.
5. Verify independent alerts and restore access. A successful dump command or same-provider copy alone does not prove offsite recovery.

The root Compose backup helpers support only the reviewed local `db/apex` target and require explicit `APEX_BACKUP_SCOPE=compose-local`, including the timer's environment file. They refuse external targets. For hosted PostgreSQL, use its separately reviewed recovery procedure. A company JSON/ZIP backup restores a **new company**, not the entire database, users or memberships; it is not a schema rollback. See [backup boundaries](../deploy/SECURE_BACKUP.md).

## Isolated acceptance, then controlled cutover

Before live execution, verify on the actual-target clone:

- Forward migration succeeds; rerunning it is a no-op; schema readiness succeeds only at the expected head.
- Stable company/record identities, journal balance, stock quantities/costs, invoice outstanding, partial allocations, bank mappings and canonical reports are unchanged by schema migration.
- Existing users can sign in under the approved session-key policy. Explicitly account for planned logout/recovery rather than discovering it at cutover.
- Old-client core journeys remain intelligible; new clients display the connected API revision and capability state. New receipts force a complete backup instead of silently disappearing from an old export route.
- A new synthetic retained receipt and encrypted complete backup roundtrip preserve exact evidence hashes and create a separate restored company, leaving the original unchanged.
- HTTPS, body/chunk limits, protected preview access, backup quotas/expiry, background-worker configuration and database concurrency behave on the intended hosting platform. Local SQLite and loopback HTTP checks do not prove provider behavior.

Then, and only with the required operational authority, coordinate writer shutdown, backup verification, standard migrations, immutable deployment and HTTPS/build-revision checks. Re-enable writers after post-cutover reconciliation. No commands in this checklist have been executed against production.

## Native distribution and source-book identity

Unsigned Android APK/AAB and Windows portable verification outputs are not a signed production release. Preserve Android signing-key/package continuity and increasing version code, review Windows distribution/trust/update behavior, and perform clean install/update/device acceptance through the intended channels. Do not request or paste private signing keys in chat.

Keep supplied books separate using explicit owner-chosen book labels; identical legal names/GSTINs are not permission to merge. Two supported supplied backups were rehearsed privately; unsupported historical adjustments in the other backups still require reviewed source correction or mapping. Do not substitute a partial import for a reconciled migration.

See [release verification](RELEASE_VERIFICATION.md) for exact source, automated/interactive evidence and the remaining browser, provider and distribution gates. This checklist does not certify tax compliance, comprehensive security or zero defects.
