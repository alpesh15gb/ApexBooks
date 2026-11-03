# SQLite company-history load: measured ordering index

## Bounded change

Migration `j129ab697cb4`, after `i018fa586ba3`, adds only SQLite index `ix_records_company_order` over company ID, descending business date, descending `coalesce(json_extract(data, '$."created_at"'), '')`, and descending record ID. The SQLite list query uses those same fixed, internal path/default literals. Previously bound path/default parameters prevented SQLite from matching an expression index, even when the equivalent index existed.

The ordering, filters, page sizes, offset/no-limit behavior, compact projection, decimal values, permissions and lifecycle/outstanding calculations are unchanged. There is no cache, polling, new endpoint, stored-row rewrite, bank-list change or client change. PostgreSQL keeps its previous query and indexes; its Alembic revision advances without index DDL. No PostgreSQL speedup is claimed. In particular, valid legacy backups can contain very long created_at values that are unsuitable for an unbounded PostgreSQL B-tree key.

## Reproduce locally

    python tests/performance/record_order_index.py

This imports the existing test_api fixture, verifies its exact disposable SQLite database, and uses independent processes/databases for 3000 and5000 rows. Each has one journal per record, two journal lines per journal, and respectively 1000/1666 split allocations. Invoices carry 20 lines and deliberately large source/branding/snapshot JSON. The benchmark uses actual TestClient GETs, compares every response field and row order, and prints query plans, SQL counts, bytes and timing samples. It creates no external network traffic.

For each mode and size: one warmup plus three read samples. Full scan includes the final empty page when count is divisible by 500. These are **warm local SQLite/TestClient wall-time medians**, not cold-process/network/device startup or production latency. The machine was shared; individual samples varied materially. Retained complete results: `tests/performance/record-order-index-results.json`.

| Synthetic records | First 500 rows, before → after | Full compact scan, before → after | Full-scan requests / SQL | Identical full payload bytes |
|---|---:|---:|---:|---:|
|3000|156.37 →65.34ms|944.32 →411.10ms|7 /46|952,898|
|5000|200.76 →58.08ms|2363.64 →540.91ms|11 /74|1,588,908|

First-page query count stays 7 and bytes stay 158,998/159,007. Baseline EXPLAIN uses the company-ID index plus temporary B-tree ORDER BY; indexed EXPLAIN uses the composite ordering index with no temporary sort. This improves work per query, not request count or wire size. The query plan and exact response equality are stronger evidence than any individual noisy timing sample.

Named banks were separately profiled: 5 and 20 accounts made 9 and 24 SQL statements respectively, confirming the existing per-bank ledger lookup. That separate N+1 issue is **not changed here**.

## Costs and rollout

Index build including commit measured 82.07ms for 3000 rows and 191.06ms for 5000 rows, using 368,640 and 610,304 bytes respectively (`dbstat`). These synthetic sizes are not production build-time guarantees. **SQLite CREATE INDEX takes schema/write locks**; back up the database and apply through a reviewed maintenance migration, with enough free space and a tested recovery plan. No production migration was run for this work.

The index must also be maintained on writes. The portable benchmark's 100-heavy-row Core INSERT statement medians were 14.17→17.76ms at3000 rows and 18.09→15.91ms at5000 rows; this noisy latter decrease is not evidence that writes become faster. An earlier isolated 5000-row probe measured 11.08→17.12ms. Row construction, rollback and durable commit latency are excluded from those write samples. Expect additional write/index-storage work; quantify it on a representative disposable deployment copy before rollout.

Downgrading this one migration drops only the added index, not records. The new query works without the index with its old slower sort. This does not authorize downgrading older accounting migrations or dropping durable journal retry bindings. Standard API readiness requires the current migration head; it is not a comprehensive index-integrity monitor.

## Compatibility and verification

- Regression tests compare compact/full responses, all supported JSON scalar/container/missing created_at types, long 12,000-character legacy values, equal-key ties across pages, kind/hidden-kind filtering, offsets with/without limits, current outstanding, archived masters, viewer access and outsider rejection.
- SQLite upgrade/repeated upgrade/downgrade preserves stored rows and long legacy values. Query-plan regression verifies index use; dropping the index preserves response values.
- SQLAlchemy metadata emits the index only for SQLite. Mocked PostgreSQL DDL emits none. PostgreSQL metadata comparison excludes only this model-only SQLite index, not an unexpected reflected or matched same-name index; live PostgreSQL execution is a separate CI gate.
- Reproduced before the fix: Alembic compare_metadata reported zero differences for an unversioned SQLite database missing this expression index. The unversioned stamping path now explicitly checks its exact expression and refuses missing/mismatched indexes before stamping. It does not repair an unversioned database automatically or ignore unrelated schema differences.

No app lifecycle or cross-device freshness guarantee follows from this optimization. Records and report cards still load through separate reads.

## Local checkpoint results

The final aggregate check passed 318 backend tests, 240 web tests, web lint/build, five HTTP acceptance cases, a 6,402,960-byte complete-backup roundtrip, 232 native route checks, nine backup preflight mocks and 30 VPS deployment mocks. The original 1.3 repository schema upgraded to `j129ab697cb4`, preserving original rows across 33 tables and canonical reports; repeated migration, receipt/complete-backup restore and restore replay passed. These were isolated synthetic operations, not live deployments.

An initial aggregate run exposed cleanup interference in the new fallback test's shared fixture. The final test uses an independent migrated database and explicitly proves index absence before and after its HTTP read, exact response equality and fallback sorting. It passed independently and in the complete suite. No product index-recreation behavior was established by the initial failure.

Local native compilation, PostgreSQL execution and age-based encrypted infrastructure-backup checks were not run. Existing hosted CI must verify PostgreSQL migration compatibility and native builds; no new browser/device permission is implied.
