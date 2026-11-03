# Disposable PostgreSQL page-projection comparison

This is a test-only comparison harness, **not a production query/index change**.
The candidate has not yet been measured on PostgreSQL; it must pass hosted CI.
PostgreSQL execution requires the dedicated disposable CI service. Local syntax
and guard tests do not establish PostgreSQL correctness or timings.

From the repository root, with dependencies already installed:

```sh
python tests/performance/test_postgres_company_load_guard.py
# APEX_TEST_DATABASE_URL must name the freshly provisioned loopback database
# apex_concurrency_test. Do not use an existing application database.
python tests/performance/postgres_company_load.py --size 3000 --date-shape same-day --output profile-3000.json
# Run in a DIFFERENT freshly provisioned database/service instance:
python tests/performance/postgres_company_load.py --size 5000 --date-shape spread --output profile-5000.json
```

The guard runs before app/engine imports, rejects non-loopback URLs, other database
names, query/fragment overrides and all nonempty PG-prefixed environment
variables. After connecting, it verifies the actual database and effective `public` schema, then refuses any existing user-schema
relations (including views/foreign tables). PostgreSQL may report a container
address behind the approved loopback Docker port; that server-internal address is
not required to be loopback. It never drops/resets a database.
Existing migrations initialize only this empty disposable database.

## Fixture and measurement

Each run inserts exactly N synthetic posted records, N journals, 2N journal lines,
N posting links, floor(N/3) allocations and 20 named banks. These are direct
read-profiling fixtures, not an end-to-end accounting posting acceptance test.
There are no item/stock records. Invoice lines and saved totals are synthetic.
Each record has roughly 36 KB of branding/source metadata plus up to 20 lines.
A fixed random seed produces high-entropy synthetic text by default, rather than
unrealistically compressible repeated letters. `--json-shape compressible` is an
explicit comparison option; run it against another fresh database. Logical JSON,
PostgreSQL column storage, heap and total relation bytes are reported to expose
TOAST/compression differences. Metadata includes absent/null/boolean/number/object/
array `created_at`, and one 12,000-character value. All content is synthetic.

`same-day` puts every record on one business date; `spread` uses 365 dates. These
are **different workload shapes**: the example 3000/5000 runs are not a controlled
row-count scaling comparison. Use equal shapes with separate fresh instances to
compare sizes, or all four size/date combinations when the CI budget permits.

After fixture creation, explicit ANALYZE initializes statistics on the relevant
read tables. Each first-page (500), deep-page (last 500), entire scan and bank-list
measurement has one discarded warmup and three retained samples PER variant.
Baseline/candidate order alternates on the same fixture. Full scan
includes the final empty page. Actual in-process TestClient HTTP time, executed
SQLAlchemy cursor-event count/time, response bytes and a result hash are reported. Repeated
reads across both variants must have identical raw HTTP bytes and values/order; first/deep pages must match the full
scan, with unique IDs, expected row counts, posted state and compact projection.

Captured first/deep record SELECTs are rerun with EXPLAIN (ANALYZE, BUFFERS,
VERBOSE, FORMAT JSON) in an explicitly read-only transaction with a 120-second statement
timeout. Plans run **after** timed samples and are not included in their times.
The artifact contains only plans, numeric statistics and synthetic result hashes,
not response bodies, credentials, tokens, authentication SQL or parameters.
Output is capped at 1 MB; progress/migration logs go to stderr. `--output` writes
pure JSON for CI artifacts. No new packages are required.

These are warm local service/TestClient measurements, not cold-process, WAN,
mobile, device or production-load guarantees. Cursor timings exclude Python
materialization/serialization, while HTTP wall time includes them and response JSON decoding. Cursor-event
counts are not a count of every driver/network round trip. Each workload
starts from a fresh database, but caches are intentionally warm during retained
samples. No optimization is justified until actual PostgreSQL results are read.

## Measured baseline and bounded hypothesis

PR37 source `136f392b`, GitHub Actions run `41691730008`, artifacts
`13257248381` / `13257274207` established the baseline on disposable PostgreSQL
17.11. Both cases used spread dates and entropy metadata. Warm first/deep/full
HTTP medians were approximately 118/245/1357 ms at 3000 records and
212/485/3983 ms at 5000. The 5000-row EXPLAIN deep page evaluated the compact
projection for 5000 rows below LIMIT (448 ms total), versus 500 on page one
(172 ms). The scan remained roughly 132–139 ms: this proposal does not remove
that scan, TOAST extraction or sort floor. No PostgreSQL index is added.

The experimental interceptor matches only the exact existing compact Record
SELECT columns, company/hidden-kind/optional-kind predicates and three ordering
expressions. It derives an inner ID/date/unchanged-created-key SELECT with the
original LIMIT/OFFSET, joins the paged IDs back to records, and performs compact
projection outside that page. It repeats original predicates and orders by the
captured keys outside. The single SQL snapshot is preserved; raw JSON is not
carried through the inner sorter. Full/noncompact, auth, status and bank reads
remain untouched. Match/rewrite counts are asserted against request counts.
`Session.execute` is patched only inside a context manager and restored on exit.
This interception adds Python query-matching overhead to BOTH timed variants;
these are comparison numbers, not an uninstrumented production latency claim.

VERBOSE plan gates require a 500-row, three-output narrow LIMIT boundary without
raw data/compact JSON, and compact-projection output nodes processing at most
500 rows. Join algorithm is not prescribed. Baseline/candidate plan structures
and projection node counts are emitted for independent review. First-page
regression from extra primary-key lookups is possible and must be considered,
not hidden by a deep-page gain.

After timings, untimed byte-equality checks cover kind filters, offset without
limit, page crossings, empty pages, unchanged full responses, an empty second
company, archived item/party data, hidden kinds, outsider denial and viewer/owner
parity. Extra edge records are confined to the second company, and are not part
of the measured storage/fixture. No actual candidate performance improvement is
claimed until the new hosted results are available.

## Incomplete diagnostic artifacts

The first PR38 comparison run (`41693817517`, source `94616bed`) reached equal
first-page responses but failed the narrow page-boundary plan assertion for both
fixture sizes. It did not establish a passing candidate or full-scan parity.
The failed run initially lost its plans because output was written only at the
end. No query or plan assertion has been relaxed to address that loss.

With `--output`, the harness now checkpoints bounded pure JSON after fixture
creation and measured modes, and **before** validating captured plans. A failed
assertion therefore leaves `completed: false`, the exact diagnostic `phase`, and
all plans/statistics captured so far. Only after every plan, snapshot and edge
check passes does it write `completed: true` and `phase: complete`. An incomplete
artifact is evidence for diagnosis, never a passing benchmark. Stdout-only mode
prints only a successful final object; CI must use `--output` and upload that
path even on failure. The 1 MB cap applies before any checkpoint replaces a
previous artifact. No credentials, response bodies or exception dumps are added.
