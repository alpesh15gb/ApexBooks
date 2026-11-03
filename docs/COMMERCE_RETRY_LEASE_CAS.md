# Commerce retry preserves concurrent worker claims

## Confirmed original behavior

PR42 source `c35f8ff24b8949303dd8f38e06cb3a291139fb0a`, disposable PostgreSQL
run `41712027669`, job `126182260301`, artifact `13268240964` reproduced the
race without any generation prototype. Both inbox and outbox retry requests read
a failed message, waited on the actual worker claim, then returned 200 and reset
the committed processing row to pending with its lease cleared (attempts 1).
The desired safety assertions failed in both directions. Valid failed-message
retries and repeated-pending rejection passed; this was not an infrastructure
failure. No external commerce delivery was performed.

## Narrow correction

The existing retry endpoint still authorizes company write access and scopes the
connection before reading the message. Its UPDATE now also requires the same
company, connection, message ID, observed status, attempts and null-safe lease.
A worker transition after that read causes a zero-row UPDATE, rollback, and 409:

`Message changed while retrying; refresh its current status before retrying`

Attempts are included because a worker can claim and fail back to `retry` with a
null lease: status and lease alone cannot detect that ABA transition. Fresh valid
`review` or `retry` requests still change that row to pending, preserve attempts,
clear the error and lease, and return the unchanged response shape. An already
pending request still returns the existing 409. This endpoint has no immutable
idempotency-key binding; neither this fix nor the tests promise exactly-once
remote delivery. No new audit events, journals, stock movements, or outgoing jobs
are introduced by retry. Existing authorization and company-lock behavior remain.

## Verification scope

- SQLite tests cover each CAS predicate and rollback using an explicit
  transaction-local injected change. This is not a claim of SQLite worker
  concurrency. Valid retries, repeated requests, viewer/foreign-company rejection,
  nullable/non-null leases and unchanged business/audit/job counts are checked.
- The dedicated PostgreSQL regression uses actual `claim`, retry API and `finish`
  methods, with mocked connection verification and no delivery processing. It
  checks both directions, observed row-lock waiting, claim/failure/ABA, and explicit
  retry of the new failed attempt. No generation table is permitted.
- Corrected PostgreSQL execution is pending the next published disposable CI run.
  The original failing evidence is retained above, not relabeled as a pass.

No production database, migration, API schema, client capability, or generation
mechanism changes are included.
