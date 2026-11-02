# Company-load performance

Synthetic local SQLite benchmark, 2 November 2026. No private or hosted records.
Run `python tests/performance/records_benchmark.py` with backend test dependencies.
Each case uses one warm-up and three measured complete HTTP pagination passes.
Rows include large source/branding snapshots and invoice/payment allocations.

| Records | Page size | Before median ms | After median ms | SQL before → after | Payload bytes before → after |
|---|---:|---:|---:|---:|---:|
| 100 | 100 | 44.53 | 35.59 | 18 → 11 | 44,596 → 31,596 |
| 100 | 500 | 33.86 | 16.26 | 9 → 7 | 44,594 → 31,594 |
| 1,000 | 100 | 1,208.68 | 672.00 | 99 → 74 | 447,905 → 316,905 |
| 1,000 | 500 | 499.31 | 202.07 | 27 → 18 | 447,897 → 316,897 |

The combined old 100-row-page to new 500-row-page path changes 11 HTTP requests to 3,
99 SQL queries to 18, and median local latency 1,209 ms to 202 ms (83% reduction).
Payload falls 29%. These are repeatable synthetic measurements, not a production
latency guarantee. Network and database contention affect real results.

Implementation: SQL-side compact JSON projection; page-scoped status/allocations;
skip irrelevant status queries and empty-page aggregate work. Compact transactions
omit full company/branding snapshots, source blobs and full-size images; detail
and document PDF retain them. Item thumbnails, dates, party IDs, payment flags,
stock metadata and fresh computed balances remain available. No cache, schema
migration, or cross-company reuse is introduced. PostgreSQL JSONB behavior has
an explicit CI parity test; this Linux executor has no PostgreSQL server.

Raw sanitized measurements are `tests/performance/records-before.json` and
`records-after.json`. Clients use the existing 500-row maximum and cancel obsolete
company requests. No claim of comprehensive security review is made here.
