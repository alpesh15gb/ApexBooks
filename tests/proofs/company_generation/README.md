# Experimental persisted-company generation proof

**TEST ONLY. Not a deployed feature, production migration, API, or real-time sync design. PostgreSQL is UNEXECUTED; release suitability is BLOCKED.**

Run from backend with the existing test environment:

    python -m unittest test_company_generation_poc -q

Run the disposable write benchmark from repository root:

    python tests/proofs/company_generation/benchmark.py

Both import test_api, which creates an isolated temporary SQLite database. The tests additionally verify that the engine names that exact synthetic database. Do not manually install this prototype on any other database. No external integration calls occur: the commerce verify response is mocked.

## One architecture, bounded scope

A separate **preseeded** company-keyed generation table receives transactional increments from row triggers. Existing companies start at0 when the proof is installed; a new company INSERT seeds its own row before incrementing. There is no FK from the counter to companies and no lazy first-write upsert. This avoids introducing a parent FK lock during a worker's first child-table write. It does not prove that a shared counter row has safe lock ordering in every transaction.

The manifest explicitly covers28 current company-owned business tables and excludes11 application tables plus alembic_version. All covered child rows already have their own company_id; companies uses id. No parent lookup is needed. It includes masters/records/settings/membership, accounts/journals/allocations, banks/reconciliation, stock, retained evidence, and all seven commerce tables. See COVERED/EXCLUDED in prototype.py for exact names and reasons.

Excluded: global users/auth/session/throttles/recovery; user/global backup staging and chunks/quota; audit and live retry bindings. Consequently an audit-only backup download and exact idempotent replay without a domain change do not invalidate. Authentication and current membership MUST be checked on every future detector request. token() is deliberately a low-level test SQL helper with **no authentication** and must never be exposed as an endpoint.

All INSERT/DELETE and meaningful UPDATEs increment the counter in the same transaction. SQLite null-safe column comparisons suppress lock-reservation name=name updates. A row reassigned to another existing company invalidates both domains. Increment is per changed row, NOT per business operation, so a financial command can advance it several times. Treat it as an opaque comparable generation, not a transaction count. Savepoint/transaction rollback rolls it back; another SQLite connection cannot see uncommitted values. Two separate SQLite processes demonstrate serialized writer increments without loss, not PostgreSQL concurrency.

## Executed versus manifest-only coverage

Tests exercise API lower-revision master archive, preferences, membership/auth exclusion, expense/journal/evidence retry, mocked commerce verify, portable restore with independent new identity, ORM mutation, Core bulk insertion, direct SQL update/delete/company reassignment, rollback/savepoint, no-op reservation update and two-process SQLite contention. Retained evidence fixture inserts a receipt and the test archives/replays it. Other covered tables are **source/manifest/trigger-definition checked, not each dynamically mutation-tested**; no comprehensive production writer certification is claimed.

Readiness in this proof checks table classification, all expected trigger SQL definitions (not just names), missing company seeds and absence of counter FK. Tests inject an unknown table, missing trigger and same-name no-op trigger. This is NOT integrated with current schema_ready, whose migration/table cache does not attest installed triggers. Future schema columns/types and counter-table corruption need explicit review; no automatic production repair is provided.

## Known exclusions and blockers

- PostgreSQL has not been executed or installed. Do not infer its row-lock behavior from SQLite's database-wide serialized writer. A Company-column counter has a concrete lock-order risk: a worker holds inbox rowR then wants CompanyC, while retry holdsC then wantsR. A **dedicated preseeded** counter avoids that particular cycle; no supported-path deadlock was established for it in this source review, but arbitrary multi-company writes/future child-first writers remain unverified.
- PostgreSQL SQLAlchemy JSON columns cannot universally use whole-row equality: JSON values need suitable jsonb comparisons. The separate authored PostgreSQL counterpart below remains unexecuted. Required proof: competing API/worker transactions, lock-order/timeouts, rollback, uncommitted visibility, and no lost increments.
- SQLite INSERT OR REPLACE can suppress implicit DELETE triggers with recursive_triggers OFF. An explicit test demonstrates moving a replacement rowA→B incrementsB but missesA. The current covered app paths do not use REPLACE, but this is an **unsupported direct-write counterexample**, not silently fixed by the prototype. A release would have to prohibit it or verify appropriate behavior on every connection. PostgreSQL TRUNCATE is likewise not covered by ordinary row DELETE triggers and is unsupported.
- Company deletion leaves a counter tombstone; IDs are not reusable. Company primary-key reassignment is unsupported (missing seed aborts). No pruning/cleanup policy or production downgrade is defined.
- Equality means only no covered persisted changes. Reservation expiry, calendar/date-dependent reports and newly accessible company-directory entries need separate invalidation. No token can make separately requested records/reports one atomic snapshot; a later design needs a scoped before/read/after consistency handshake, not attaching a newer token to older loaded rows.
- Excluding audit means an audit-only change is deliberately outside token scope. Excluding auth never permits cached authorization. Staging UI needs its own user/global scope.
- A sequence/MAX append-log alternative was not implemented: allocation order is not commit order (slow sequence10 can commit after observed11 without changing MAX). Count-only append logs avoid that specific problem but add unbounded storage and O(history) reads. There is only one prototype here.

## Bounded write-amplification measurement

Local isolated SQLite, one warmup then five statement-time samples. Insert100 or1000 synthetic party rows through one Core executemany; generate payload before timing, rollback every sample, and exclude setup/rollback/commit latency. SQLite total_changes includes trigger updates; it is not a count of network round trips or SQLAlchemy emitted statements.

| Rows | Baseline median | Prototype median | SQLite row changes baseline → prototype |
|---|---:|---:|---:|
|100|1.060ms|1.211ms|100 →200|
|1000|9.541ms|12.814ms|1000 →2000|

Each covered row mutation adds one generation-row update (a cross-company move adds two). These environment-specific numbers do not estimate production latency, financial-command cost, large-blob UPDATE comparisons, durable commits, or PostgreSQL contention. No polling/client behavior or production source was changed.

## PostgreSQL counterpart: authored, not yet executed

The separate `postgres_prototype.py` and `test_postgres_generation.py` are a
**test-only** counterpart, not an application migration or endpoint. The SQLite
results above do not prove these PostgreSQL paths. Local checks compile Python
and validate generated SQL/URL policy only:

    python tests/proofs/company_generation/test_postgres_generation_sql.py

Hosted execution must use a freshly provisioned disposable loopback PostgreSQL
`apex_concurrency_test` database, then run:

    python tests/proofs/company_generation/test_postgres_generation.py --output generation-pg-proof.json

The harness rejects remote/other databases, query/fragment URI overrides and all
nonempty PG-prefixed environment settings before importing the app. It verifies
actual database identity/effective public schema and refuses any existing
non-system relation. It never imports `test_api`, drops a schema or resets existing
data. It applies only the existing app migrations to the fresh fixture, then
installs the isolated proof objects. No app startup/schema_ready code imports them.
No external commerce request runs: verify is mocked, and worker testing invokes
only `claim`, not network delivery/processing. A synthetic encryption key is
created in-process and never emitted in artifacts.

### Exact proposed trigger and lock scope

The existing 28-table manifest is reused. Each row trigger calls a dedicated
preseeded bigint counter without a Company FK or lazy upsert. Company insertion
seeds the row; missing seeds abort, company-ID changes are unsupported, deletion
leaves a tombstone. Updates compare ordinary columns with IS DISTINCT FROM and
JSON columns via `::text`, since PostgreSQL JSON lacks equality. Text comparison
is intentionally conservative: equivalent differently serialized JSON may cause
extra increments, never an assertion that every increment represents a semantic
business change. Large JSON/blob comparisons can be expensive; this is not a
performance qualification. No-op self-updates and exact replay are tested.

One cross-company row move updates both G rows in sorted ID order. This is **not
transaction-global deadlock prevention**. The negative control first mutates A
in one transaction and B in another, then moves their distinct rows in opposite
directions. It observes the wait edges through pg_blocking_pids, requires one
actual `40P01` deadlock victim and one commit, and verifies only the committed
transaction's three increments survive. A generic lock timeout is not accepted
as proof of that cycle. This remains a deployment blocker for arbitrary
multi-company transactions/future writers; no automatic retry or global-order
fix is introduced.

The supported commerce proof pauses the actual retry endpoint after Company C is
locked and actual claim after inbox R is locked. Retry reads then waits for R;
the test observes that wait, releases claim to update G and commit, then requires
retry to finish and the generation to increase twice. The traced graph is claim
R→G→commit versus retry C→R→G. This avoids a Company-column counter's R→C edge,
but does not certify every future G→child path. Inbox processing and other worker
paths are source-traced rather than all dynamically exercised.

The existing retry endpoint performs a nonlocking status read followed by an
unconditional ID update. It may overwrite a newly claimed lease after waiting;
the artifact records final status/lease state rather than asserting nonexistent
409 or exactly-once guarantees. This proof does not fix that separate application
behavior.

### Authored execution and exclusion checks

- Rollback/savepoint/uncommitted visibility, ORM/Core/bulk mutation, no-op JSON
  update, archive/preferences and exact financial retry.
- Two separate Python processes commit independent row changes with no lost
  increments; child waits and cleanup are bounded. This case does not force
  overlapping transactions; deterministic contention is covered separately by
  the commerce and multi-company barriers.
- Same-company actual claim/retry ordering plus the retained unsupported
  multi-company cycle above.
- Current membership changes versus excluded account/auth writes, new restored
  company identity without portable counter bindings, retained receipt insertion,
  archive and replay, and mocked commerce verification.
- Mocked clock expiry changes active reservation quantity without a database
  write or generation change. Time-derived invalidation remains separate.
- TRUNCATE on synthetic reservations intentionally demonstrates no row-trigger
  increment, then rolls back. SQLite REPLACE remains the separately demonstrated
  unsupported case above; it is not a PostgreSQL operation.
- Readiness checks expected public function bodies and namespaces, trigger
  table/event/enabled state,
  seed presence and no counter FK. Disabled/changed triggers and missing seeds
  are injected in rolled-back transactions. Privileged trigger bypass, direct
  counter edits and unsupported TRUNCATE are not magically prevented.

Statement/lock timeouts are reset per transaction, including rollback on a reused
connection, and bound fixture database operations, explicit events bound
coordination, and subprocesses are terminated on failure. The hosting job remains
an outer bound for thread shutdown or connection failures; this is not a general
process supervision guarantee. Artifacts contain test counts, bounded synthetic
outcomes and limitations, not credentials or response bodies. Most manifest
entries still lack individual dynamic writer tests. No release suitability,
change-detection endpoint, polling loop or real-time client behavior is claimed.

### Isolated hosted proof

`company-generation-proof.yml` supplies a fresh PostgreSQL 17 service with a
synthetic job-only credential and dynamic loopback port. It runs the pure guard
checks first, then the standalone script. The script verifies the exact database
identity, public search path and absence of all user relations **before** running
existing migrations or installing proof objects. It never drops or resets an
existing database. No repository secrets, production connection or live/external application
endpoint is used; local synthetic TestClient routes are exercised. The 15-minute job bound complements statement, lock and event
timeouts. Only the bounded synthetic result JSON is uploaded for seven days;
startup failures remain visible in job logs if no result exists.

This workflow is proof-only. Passing expected negative controls does not make the
generation mechanism deployable, eliminate the listed omissions, or establish a
real-time client guarantee. Actual PostgreSQL results are pending until this
exact checkpoint executes on the hosted disposable service.

### First hosted attempt and diagnostic correction

PR41 source `283cfbafec90c1bde9641f37dc7be07bbbaa6805`, run
`41709757823`, job `126174426983` reached PostgreSQL 17.11 and completed
existing migrations plus proof function/trigger creation. Startup readiness then
failed because raw `exec_driver_sql` LIKE patterns contained unescaped percent
characters interpreted by psycopg. No concurrency tests ran and that attempt
produced no result artifact. The corrected proof binds both LIKE patterns through
SQLAlchemy `text`; a local psycopg-query-parser regression checks the actual
readiness statements without a database. Bounded incomplete JSON is now written
before startup and updated at each phase, without exception strings, URLs, or
credentials. Actual PostgreSQL proof results remain pending a corrected CI run.

### Hosted PostgreSQL evidence (2026-11-03)

Corrected source `95c3522244d28fa76c783e065d8cf52274631b9f` completed
[proof run 41710281324](https://github.com/alpesh15gb/ApexBooks/actions/runs/41710281324),
job `126176247182`, on disposable PostgreSQL 17.11. Four pure checks and seven
actual PostgreSQL tests passed; the latter ran in 3.439 seconds. Artifact
`13267907949` contains the bounded `result.json` with `completed=true`, seven
tests, zero failures and zero errors. This supersedes the pending-execution note
above for this exact source only.

The passing suite deliberately includes failures of the proposed design:

- Opposite multi-company transactions produced observed mutual blocking, one
  `40P01` deadlock victim and one committed transaction. Rolled-back increments
  disappeared. Per-row sorted counter locking is not a global lock-order proof.
- Actual commerce claim/retry methods completed after an observed row-lock wait,
  incrementing generation twice. Final inbox status was `pending` with its lease
  cleared: the existing retry endpoint overwrote a newly claimed lease. The
  generation proof did not correct or establish exactly-once commerce handling.
- Reservation expiry changed availability without a generation increment;
  TRUNCATE was also unobserved. The separate SQLite REPLACE omission remains.

Rollback/savepoint/visibility, no-op/replay, two independent process commits,
readiness negative controls, membership, synthetic restore and retained evidence
checks passed within their stated scope. This is not exhaustive writer coverage,
a performance qualification or a production-ready freshness token. The prototype
remains **unshippable**; no application migration, endpoint or watcher was added.

Other checks on the same source were terminal: main CI `41710281043` and unsigned
Release `41710281134` passed; Android device `41710280975` was intentionally
skipped. Windows UI `41710280969` failed at an owned Open-picker lookup. Its
artifact `13267883603` showed a visible enabled picker owned by the launched
process's current main window, while the harness cached an invisible different
window and found no matching top-level UIA candidate. No application or picker
trust-rule change is included here, and this run is not reported as a UI pass.
