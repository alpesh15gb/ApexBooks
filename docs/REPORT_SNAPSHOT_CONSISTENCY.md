# Financial report snapshot consistency

## Confirmed concurrent-read defects

The financial report previously queried period movement and cumulative balances separately. If another client committed a second INR 100 invoice between those queries, an April report with no opening activity could return net profit and receivable period movement of INR 100 alongside retained earnings and closing receivable of INR 200. Its balance-difference check still showed zero because that check used only the later cumulative values.

Account identities were also queried separately from journal lines. A concurrent first posting could introduce a new system account between those reads, causing a missing-account exception in the financial report or trial balance.

## Scope

The correction obtains account identities and dated journal lines from one company-scoped SQL statement, then derives totals from that fixed result. Existing decimal arithmetic, sign conventions, zero-balance accounts, report shapes and inclusive date boundaries remain unchanged. No posting, balance, date, accounting classification or authorization is changed. The existing financial-report cumulative lower bound of 1900-01-01 is retained in this bounded concurrency fix; trial balance retains its existing unbounded beginning.

Independent review of party statements and receivable/payable ageing found no discrepancy across 34 synthetic as-of snapshots, including opening balances, split settlements, advances, return credits, archived masters, opening/range boundaries and party filters. Current-summary receivable/payable fields retain their documented all-posted-activity semantics rather than becoming period totals.

## Verification

Eleven focused tests passed; independent review reran six focused snapshot/settlement tests and the 34 date-boundary snapshots without finding a discrepancy. Regression cases interleave a committed posting after the single query result is captured and before serialization, including an initially empty chart of accounts. A dedicated PostgreSQL read/post barrier regression is added; execution awaits hosted CI.

The reproducible local benchmark is `python tests/performance/report_snapshot.py` with backend development dependencies. It refuses an external acceptance API and creates a synthetic temporary SQLite database. With 2,000 journals / 4,000 lines, seven-run medians were 30.44 ms for the old read and 30.72 ms for the new read; queries decreased from four to one and movement rows read from 6,000 to 4,000. This is a consistency correction with fewer round trips, not a measured local CPU speedup or production latency claim. Scalar account metadata avoids ORM lazy reads; decimal totals remain accumulated without SQLite floating-point SUM.

Full local aggregate passed: 275 backend tests; 169 web tests, lint and production build; five isolated HTTP tests; a 6,402,965-byte complete-backup roundtrip in 13 bounded chunks with archived evidence hashes retained; 232 matched native routes; nine backup-target and 21 management mock tests plus simulated backup/restore safety checks. The encrypted infrastructure-backup CLI check was not run because `age` and `age-keygen` are unavailable. No new client implementation or device run is involved. Hosted CI remains the immutable-checkpoint verification gate. No main, production, migration, browser or device actions are involved.
