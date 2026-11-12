# Master import recovery: verified boundary and proposed durable receipt

Status: investigation and implementation design, not an implemented receipt API.
No production data or external services used.

## Verified current behavior

`main.import_masters` holds the company write lock, builds a casefold/trim name
set across all masters of the chosen kind (including archived ones), validates the
batch, then commits rows and audit together. Unchanged retries create zero new
masters when the first import committed. The original response says created=1;
the retry says created=0, duplicates=1. This is name-based deduplication, not replay
of the original operation result.

A proposed concurrent rename scenario was tested and **did not reproduce**:
`update_master` rejects name changes with 422. Archiving the original also does not
permit recreation by unchanged import. The prior coverage note's rename concern
was hypothetical and is corrected here. No economic duplicate was demonstrated
through these supported operations.

The route does not inspect Idempotency-Key. A caller cannot use a key to prove
which import created a record, recover the original result or reject a different
payload using that key. The web form currently does not freeze an uncertain import
as an exact operation. Do not advertise exact replay or infer original completion
from a bounded name search. Existing record-level IdempotencyKey requires one
record_id and cannot represent an empty/all-duplicate batch or its original counts.

## Proposed implementation contract

1. Add a dedicated master_import_receipts table with company foreign key, actor ID,
   operation key, versioned canonical request hash, committed response JSON,
   created record IDs and timestamp. Unique(company_id, operation_key). Store no
   raw CSV, credentials or image payload in the receipt. Hash normalized validated
   input with an explicit route/version domain; preserve row order. Do not silently
   rewrite semantically different values into one hash.
2. Enforce current company write authorization before receipt lookup. Under the
   existing company lock, look up the key before validation dependent on changing
   masters. Matching actor/hash returns the original committed result. Different
   payload/actor returns 409 without exposing another actor's response. Invalid
   keys reject before writes. A key is mandatory for the new capability; old clients
   can retain legacy behavior until migrated, with no replay guarantee claimed.
3. Insert masters, audit event and receipt in the **same transaction**. Reject whole
   invalid batches with no receipt. Retain receipts for all-duplicate/zero-created
   valid batches. Concurrent identical requests must produce one operation and
   identical responses; unique constraint remains a backstop to the company lock.
4. Expose an authorized GET receipt lookup by operation key. A missing receipt is
   not proof of failure while a transaction may still be running. Keep original
   payload/key frozen in memory; retry only the same keyed request. For reload,
   preserve at most the opaque key and company/actor identity, not CSV/PII in browser
   storage. Lookup can recover a committed result; missing/in-progress outcomes
   require source-file reselection and exact hash matching or continued checking,
   never an automatic new key.
5. Keep receipts scoped to the original company/database. Company backup restore
   must not transplant them as valid receipts for a new company. Specify complete
   database restore behavior separately. No silent expiry: retain a tombstone/key
   binding if response retention is bounded, so old keys cannot become new writes.
6. Advertise capability only after migration and API support. Web/Windows/Android
   must use one key/body per operation, retain unknown 408/5xx/network outcomes,
   show original-result recovery and distinguish confirmed import from refresh
   failure. An older server must not show an unsupported exact-retry promise.

## Required validation before calling this implemented

SQLite and PostgreSQL migration upgrade/rollback and concurrency; committed lost
response, uncommitted interruption, all-duplicate batch, changed same-key payload,
actor/company/role isolation, revoked access, invalid-batch atomicity, archive/edit
between attempts, exact returned created IDs/counts, receipt retention and separate
company restore. Actual web access-loss/remount/reload and native transport tests
must verify the original key/body; physical device acceptance remains separate.

Current executed evidence: one unittest with two synthetic lifecycle subcases
(active and archived), proving unchanged retry does not duplicate and renaming is
rejected. No durable receipt or new recovery UI has been implemented by this batch.
