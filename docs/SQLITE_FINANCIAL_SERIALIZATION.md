# SQLite financial-write serialization

## Reproduced defect

Two concurrent synthetic API requests applied 60 each from the same customer advance of 100 to an invoice of 100. Both returned success and posted distinct applications, leaving both the available advance and invoice outstanding at -20. The reproduction changed only request timing: it paused both requests after their balance checks and before insertion.

The company write helper used `SELECT ... FOR UPDATE`, which SQLite ignores. PostgreSQL's existing row-lock behavior is not implicated by this reproduction. Some numbered posting routes happened to reserve a writer earlier; advance applications and credit settlements cannot rely on that incidental behavior.

## Correction

For SQLite, the shared company write helper performs a no-op update of the existing company name before reading financial balances. This reserves SQLite's single database writer until the existing transaction commits or rolls back. A competing request then checks the newly committed remaining balance rather than a stale value. The stored company name is unchanged, and the update does not flush unrelated pending ORM objects.

Authorization is refreshed and checked after the reservation/row lock is acquired. Unflushed changes to the company or its membership are rejected rather than silently discarded by that refresh. PostgreSQL continues to use its existing row lock. There is no schema migration, endpoint change, new client capability, financial-payload cache or automatic retry.

SQLite serializes writers across the database, not merely within one company. This correctness fix does not promise improved write throughput. Existing database busy timeouts still apply. It also does not make a client request survive process death; clients still need their original idempotency key to replay an uncertain financial submission safely.

## Synthetic acceptance

`backend/test_sqlite_financial_serialization.py` covers:

- Competing advance apply/apply, apply/refund and refund/apply: only one 60 posting succeeds, leaving 40 available; no negative invoice balance.
- A credit application competing with a refund uses one shared available balance.
- Concurrent identical-key application retries return the same record and add one journal.
- Rejected input and a failure before commit roll back completely, release the reservation and permit a safe original-key retry.
- Cross-company access is rejected; stale ownership/membership is refreshed before writes.
- Lock acquisition does not flush an unrelated pending record or discard a dirty company name.

The concurrent regression synchronizes requests before lock acquisition and briefly holds the first transaction. It never places a two-request barrier inside the serialized section. Tests use isolated synthetic SQLite data. PostgreSQL concurrency remains a separate hosted gate; a SQLite test pass is not evidence of a PostgreSQL run.

## Verified local checkpoint (2026-11-03)

The aggregate isolated suite passed: 225 backend tests, 146 web tests plus lint/build, five HTTP journeys, complete-backup HTTP round trip, 232 native route literals with zero unmatched routes, and 9 + 21 deployment/backup mock checks. The focused affected modules passed 24 tests. Existing concurrency fixtures now synchronize before the writer reservation; the import CAS test still forces a real intervening master edit through the low-level migration entry point and verifies complete rollback before a successful fresh API import.

Local PostgreSQL execution and native builds were not performed for this backend-only patch. Real encrypted infrastructure-backup CLI checks were not run because `age` and `age-keygen` are unavailable; this is separate from the passing company complete-backup HTTP test. No production database, deployment or main branch was modified.
