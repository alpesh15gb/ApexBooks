# Disposable PostgreSQL company-load baseline

This is a measurement harness, **not a query/index change or performance result**.
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
measurement has one discarded warmup and three retained samples. Full scan
includes the final empty page. Actual in-process TestClient HTTP time, executed
SQLAlchemy cursor-event count/time, response bytes and a result hash are reported. Repeated
reads must have identical values/order; first/deep pages must match the full
scan, with unique IDs, expected row counts, posted state and compact projection.

Captured first/deep record SELECTs are rerun with EXPLAIN (ANALYZE, BUFFERS,
FORMAT JSON) in an explicitly read-only transaction with a 120-second statement
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
