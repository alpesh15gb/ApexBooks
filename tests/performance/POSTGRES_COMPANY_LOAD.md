# Disposable PostgreSQL page-projection comparison

This is a test-only comparison harness, **not a production query/index change**.
Both test-only candidates completed the original heavy-workload PostgreSQL
comparisons below. Neither established a clear first-page gain. An additionally
authorized workload matrix also completed for the unchanged V2 query. Its
initial-request regressions and warm-read tradeoff are recorded below.
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
The heavy payload has roughly 36 KB of branding/source metadata plus 20 lines;
medium uses 5 KB plus 10 lines, and lean omits branding/source metadata with one
line. Payment rows have no lines. The mandatory 12 KB legacy-key outlier remains
in every fixture, including tiny lean histories.
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
stops at its first short page: an empty terminal page for exact multiples of 500,
or the short first page for the tiny 25/250-row fixtures. Actual in-process TestClient HTTP time, executed
SQLAlchemy cursor-event count/time, response bytes and a result hash are reported. Repeated
reads across both variants must have identical raw HTTP bytes and values/order; first/deep pages must match the full
scan, with unique IDs, expected row counts, posted state and compact projection.

Captured first/middle/deep record SELECTs are rerun with EXPLAIN (ANALYZE, BUFFERS,
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
samples. The completed measurements below show a tradeoff, not an unconditional
optimization recommendation.

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

VERBOSE plan gates require an expected-page-row-count (up to 500), three-distinct-output narrow LIMIT boundary without
raw data/compact JSON, and compact-projection output nodes processing at most
the expected page row count. Join algorithm is not prescribed. Baseline/candidate plan structures
and projection node counts are emitted for independent review. First-page
regression from extra primary-key lookups is possible and must be considered,
not hidden by a deep-page gain.

After timings, untimed byte-equality checks cover kind filters, offset without
limit, page crossings, empty pages, unchanged full responses, an empty second
company, archived item/party data, hidden kinds, outsider denial and viewer/owner
parity. Extra edge records are confined to the second company, and are not part
of the measured storage/fixture. The completed results below quantify this candidate’s slower first page and
faster deep/full reads; they do not establish a universal performance improvement.

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

### Observed first-page cost and structural-check correction

The diagnostic rerun captured a 500-row inner LIMIT with the three intended
outputs, but PostgreSQL repeated the **identical** created-key expression twice
in its VERBOSE Output array. The earlier literal array-length check therefore
rejected a narrow page incorrectly. The checker now deduplicates only exact
Output strings and requires precisely the same-alias ID, date and exact observed
COALESCE-created-key expression. Raw data, arbitrary fourth fields, a different
expression, missing LIMIT or incorrect row count still fail. SQL is unchanged,
and compact projection must still process at most 500 rows.

The observed first-page candidate was **slower**, not faster: baseline/candidate
medians were 161.681/220.067 ms at 3000 rows and 229.223/327.356 ms at 5000. The
extra join and outer sort are visible, but do not explain the main measured
penalty by themselves: the inner scan took approximately 127 versus 71 ms at
3000 rows and 239 versus 145 ms at 5000, with 46070 versus 23068 buffer hits in
the 3000-row case. The extra outer scan was only about 1 ms. Repeated created-key
extraction causing extra TOAST/JSON work is a possible explanation, not an
established causal result. These incomplete runs do not
establish deep/full-scan benefit or passing edge checks. The next complete run
must expose that tradeoff rather than treating successful structure as a speedup.

Raw Output arrays and buffer/timing data remain unchanged in artifacts: exact
string deduplication is a structural validation step, **not evidence that duplicate
expression evaluation is free**. The candidate inner scan showed roughly twice
the buffer hits in these first-page plans, alongside higher scan time; duplicate
created-key extraction is a possible contributor requiring further evidence.
The accepted narrow LIMIT must execute once, not repeat a 500-row page in loops.

## Completed comparison: mixed tradeoff, not a shipped optimization

Source `e7fcb2aa`, hosted run `41696559672`, artifacts `13261091455` /
`13261191572` completed both PostgreSQL 17.11 cases. Both artifacts report
`completed: true`; all 11 untimed edge checks, byte-identical responses across
variants, narrow 500-row page boundaries and at-most-500-row compact projections
passed. Warm TestClient wall-time medians (baseline → candidate):

| Synthetic records | First page | Deep page | Complete scan |
| --- | --- | --- | --- |
| 3000 | 147.684 → 201.435 ms (**36.40% slower**) | 314.127 → 204.626 ms (34.86% faster) | 1726.196 → 1360.882 ms (21.16% faster) |
| 5000 | 225.358 → 313.394 ms (**39.06% slower**) | 526.315 → 309.885 ms (41.12% faster) | 4281.888 → 3506.356 ms (18.11% faster) |

Percentages use `(candidate / baseline - 1) × 100`, with decreases described as
faster. These are warm, synthetic 3000/5000-row, spread-date, high-entropy-metadata
PostgreSQL measurements with instrumented in-process HTTP. They establish neither
WAN/native latency nor cold-start behavior. The test-only candidate improves
later pages and complete scans while materially delaying the first page; it is
**not an unqualified first-load improvement**. No application query optimization,
index or deployment has shipped from this experiment. Raw artifacts are retained
with the hosted run, not copied into the repository.

## Second test-only variant: original sort-expression reuse (completed)

The next candidate is explicitly labelled
`shared_original_created_order_expression_v2` in every partial/final artifact.
It selects the exact expression object already present in the original query’s
created-key ORDER BY, rather than constructing a second equivalent expression.
Compilation now uses one shared created-key/default bind pair in SELECT and ORDER
BY, instead of two equal-valued pairs. Original predicates, ordering, LIMIT/OFFSET
and outer captured-key ordering remain unchanged. A compile/identity regression
asserts this reuse; all byte-parity and actual-plan gates remain in force.

The completed figures above belong only to the first candidate. The second
variant’s separately measured results follow; no application SQL, index or
deployed behavior is changed.


Source `551adf9d`, hosted run `41697721013`, artifacts `13261128271` /
`13261387458` completed both V2 cases with `completed: true`. Exact response-byte
parity and all 11 edge checks passed. The captured narrow LIMIT emitted exactly
three outputs for 500 rows, and compact-projection bounds passed. Warm TestClient
wall-time medians within each V2 run (baseline → candidate):

| Synthetic records | First page | Deep page | Complete scan |
| --- | --- | --- | --- |
| 3000 | 94.731 → 97.653 ms (**3.08% slower**) | 188.252 → 99.544 ms (47.12% faster) | 1079.168 → 680.801 ms (36.91% faster) |
| 5000 | 212.236 → 211.605 ms (0.30% faster) | 492.632 → 213.328 ms (56.70% faster) | 4052.973 → 2404.462 ms (40.67% faster) |

V2 improves deep/full scans in these workloads but shows **no clear first-page
gain**. Warm hosted-machine variation means V1 and V2 absolute timings must not
be compared directly; each percentage uses its own alternating same-fixture
baseline. These remain synthetic PostgreSQL 17 measurements, not cold-process,
WAN or native-device guarantees. The agreed first-page objective was not met, so
this investigation stops with the documented tradeoff. No further candidate or
application optimization is proposed or shipped from this experiment.


## Expanded workload assessment (completed; unchanged V2 query)

A new, separately authorized test-only assessment uses six fresh disposable jobs:
25 lean, 250 medium, 3000 lean, 3000 medium, 3000 heavy and 5000 heavy. The
`--payload lean|medium|heavy` argument is validated, as are the bounded record
sizes. Dates remain spread by default. The fixture version is `payload_matrix_v1`;
an explicit equal-date/equal-created-key pair is present even in tiny histories.
The candidate remains `shared_original_created_order_expression_v2`, not a new
algorithm. Prior heavy-run results must not be relabelled as this matrix’s result.

First, middle, deepest and complete reads retain alternating warm samples and
exact HTTP-byte/order parity. Page bounds adapt to tiny histories. The initial
pair for each mode is retained separately from warm medians; `--initial-variant`
can alternate which variant runs first. These observations follow fixture writes
and ANALYZE and **are not cold-cache measurements**. A fresh connection or app
process would not clear PostgreSQL/OS caches; no privileged cache reset, server
restart or cold-disk guarantee is attempted.

After timings, four simultaneous read clients run for each variant. One global
interceptor is scoped to each batch, with synchronized counters and no overlapping
engine timing listeners. Each response must equal its corresponding serial
reference byte-for-byte. This is an untimed correctness check, not a throughput
benchmark or concurrent financial-write test.

A separate synthetic party-only company supplies captured, actual first/deep
record SELECTs. A second connection holds a transaction that changes a record’s
ordering key and visible metadata together. Baseline and candidate must both see
the complete old page while the writer remains uncommitted, then the complete new
page after commit. The writer uses a scoped update and rolls back on failure.
This tests visibility under a genuinely overlapping writer, **not a commit during
an executing SELECT**, and not atomicity of all status queries in an HTTP response
or multiple pages in a scan. No production query, migration or index changes.

The writer check independently constructs every expected projected row and first/
deep ID order from the seeded fixture, rather than treating baseline equality as
truth. It asserts exactly one scoped row was updated, and sets 15-second statement
and 5-second lock timeouts on its direct reader/writer transactions. Concurrent
HTTP futures have 120-second waits, but Python cannot cancel a running HTTP worker
and executor shutdown may still wait; the workflow’s 15-minute job timeout is the
outer bound, not a claimed fully bounded 120-second batch.


### Completed six-workload results and stopping decision

Source `5ea40e46`, hosted run `41700907574`, completed all six artifacts named
`postgres-company-load-{size}-{payload}.json`. Every artifact has `completed: true`.
All 11 edge checks, exact HTTP-byte/order parity and expected-page projection
bounds passed. Four concurrent readers per variant matched serial bytes in each
case. The four captured first/deep queries also passed the independent complete
old/new-row expectations around the open writer transaction. This remains the
limited query-visibility proof described above, not whole-response atomicity.

Warm wall-time medians, baseline → unchanged V2 candidate (milliseconds):

| Records / payload | First page | Change | Complete scan | Change |
| --- | --- | --- | --- | --- |
| 25 / lean | 11.857 → 11.725 | −1.11% | 10.535 → 10.550 | +0.14% |
| 250 / medium | 40.666 → 40.918 | +0.62% | 40.056 → 40.244 | +0.47% |
| 3000 / lean | 53.906 → 54.958 | +1.95% | 469.323 → 355.065 | −24.35% |
| 3000 / medium | 91.666 → 91.449 | −0.24% | 917.639 → 614.724 | −33.01% |
| 3000 / heavy | 136.285 → 136.501 | +0.16% | 1545.651 → 962.814 | −37.71% |
| 5000 / heavy | 176.966 → 174.797 | −1.23% | 3380.416 → 1915.942 | −43.32% |

Initial first-page observations after seeding/ANALYZE, one sample per variant,
excluded from those warm medians (milliseconds):

| Records / payload | Variant run first | HTTP baseline → candidate | Change | Cursor baseline → candidate |
| --- | --- | --- | --- | --- |
| 25 / lean | Baseline | 18.697 → 14.452 | −22.70% | 3.920 → 3.042 |
| 250 / medium | Candidate | 42.348 → 51.434 | +21.46% | 17.633 → 19.240 |
| 3000 / lean | Baseline | 62.069 → 117.454 | +89.23% | 18.167 → 18.395 |
| 3000 / medium | Candidate | 94.131 → 155.135 | +64.81% | 56.052 → 58.082 |
| 3000 / heavy | Baseline | 146.550 → 221.752 | +51.31% | 109.237 → 109.359 |
| 5000 / heavy | Candidate | 233.621 → 190.007 | −18.67% | 164.370 → 157.247 |

Four of six initial candidate observations materially regressed, with most of
the extra elapsed time outside the recorded SQL cursor duration. **The cause is
unproven**: these single observations do not isolate Python compilation,
serialization, scheduling, cache effects or any other explanation. Alternating
which variant runs first is useful context, not a cold-cache control. Fixture
writes/ANALYZE already warm caches; there is no cold-OS/disk, WAN or native-device
measurement. Hosted-machine variation also prevents direct absolute-time
comparisons with earlier runs.

Warm multi-page completion gains therefore do not justify a warm-only product
recommendation under the agreed first-load stopping criterion. The assessment
stops with this documented tradeoff; the V2 query remains test-only. No application
query, index, migration or deployed setting changed, and no further candidate is
part of this assessment. Raw artifacts remain attached to the hosted run.
