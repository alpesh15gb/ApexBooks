# Web release review — 12 November 2026

This pass addresses the remaining web performance, keyboard/screen-reader and
concurrent-accounting checks from the workspace revamp. The updated synthetic
preview runs at `http://127.0.0.1:5173`. No production database was used.

## Corrections

- Financial reports could fail when a concurrent posting created a ledger account
  between queries. Accounts, period balances and closing balances now come from
  one SQL snapshot. Financial statements and trial balance share that calculation.
  A PostgreSQL regression deliberately creates new accounts during the report read.
- Heavy workspaces load when opened. A failed feature download shows a local error
  and retry action while navigation remains usable; retry after network recovery
  was verified. Reload respects open forms and pending postings.
- Search, Create menus, nested confirmations, removed invoice/payment rows and
  master forms now preserve useful keyboard focus. Background search cannot open
  behind a dialog. Errors are announced, repeated allocations have contextual
  names, and mobile report tables retain their column-header semantics.
- Real 400% zoom exposed horizontal overflow and fixed invoice bars covering
  fields. Narrow pages now reflow and short-height invoice forms scroll as one
  panel. Focused customer/rate fields remain visible.
- Actual NVDA output exposed an incorrect password label that included the reveal
  button's text. The input now has its own explicit label; the spoken retest passed.
- Cancelled invoices/bills are excluded from return and payment source choices.

## Verification

| Check | Observed result |
| --- | --- |
| Backend suite | All 252 tests pass after the report snapshot correction; evidence `tmp/backend-web-release.log` |
| Frontend suite | 144 tests pass; ESLint and production build pass |
| Bundle budget | Initial JavaScript 125,900 gzip bytes; CSS 34,803 gzip bytes; largest JS chunk 244,368 bytes |
| Measured initial transfer | JavaScript reduced from 166,358 to 125,782 bytes (24.4%); initial JS/CSS transfer reduced 20.0%. Final small accessibility changes are reflected in the bundle budget above |
| Performance regression guard | `npm run build` checks the complete static import graph against 150 KB gzip JS, 45 KB gzip CSS and 500 KB per JS chunk; limits were not raised to hide warnings |
| PostgreSQL concurrency | 16 tests pass, including conflicting retries, over-allocation, cancellation/payment races, competing edits and report snapshot consistency |
| PostgreSQL HTTP journeys | 5 lifecycle tests pass, covering purchases, returns, banking, advances/refunds, exports and access controls |
| Web trading journey | 20 independent amount/stock/report checks pass in Chromium, Firefox and WebKit; also passes against real PostgreSQL with two API workers |
| Broad screen matrix | 122 Firefox layout/axe captures pass, supplementing the earlier 122 Chromium captures. All captured states have zero axe violations |
| Focused accessibility | Final Firefox keyboard/semantic journey passes. Chromium real 200%/400% zoom review passed 22 checks and 18 captures; subsequent master-form focus correction passed its focused rerun |
| Spoken screen reader | NVDA 2026.3.1 + installed Chrome: sign-in labels/errors, search names/positions, invoice dialog focus, required fields, rate input and uncertain-save/retry announcement verified through actual Speech Viewer output |
| Dependency audit | npm production dependency audit and pip-audit of backend requirements report no known vulnerabilities at this review |

The final PostgreSQL workload used eight concurrent clients and two API workers:
300 invoices, 300 partial receipts, 30 expenses, 30 stock returns, 60 report reads
and 10 idempotent replays. Its concurrent phase completed 390 requests in 15.25
seconds with zero errors. The invoice/payment endpoint's p95 was 510.156 ms.
Trial balance reconciled to 57,630 on both sides; stock reconciled to 130 units
and 7,800 carrying value. These are local measurements, not a production capacity
guarantee. Earlier failed runs were retained: one exposed the report race fixed
above, while a separate run's two HTTP timeouts were not reproduced in subsequent
diagnostic runs. A pre-fix 1,000-invoice workload also passed, but is not substituted
for final regression evidence.

## Reproducibility and evidence

- [Web test commands](../tests/e2e/README.md)
- [PostgreSQL test commands](../tests/concurrency/README.md), including `--browser-business`
- [Keyboard, tree and zoom detail](WEB_ACCESSIBILITY_REVIEW.md)
- Browser evidence: `tmp/web-release-firefox`, `tmp/web-release-firefox-final`,
  `tmp/web-business-dev2`, `tmp/web-webkit-dev`
- PostgreSQL final evidence: `tmp/postgres-browser-release-fixed`
- Performance: `tmp/web-performance/metrics.json`; final build gate runs through
  `frontend/scripts/check-bundle.mjs`
- Spoken output and captured transcripts: `tmp/screenreader/acceptance.md`
- Dependency results: `tmp/web-dependency-audit.json`, `tmp/backend-dependency-audit.json`

Firefox's downloaded runtime could not start from its original Windows AppData
location (side-by-side assembly error). An unchanged copy under ignored `tmp`
launched successfully; executable/library hashes matched and no host configuration
was changed. The runner accepts an explicit matching runtime path for this case.
[Playwright's browser builds](https://playwright.dev/python/docs/browsers) provide
engine coverage; WebKit on Windows is not an actual iPhone/Safari device test.

All test data is synthetic. Owned test processes were stopped; the separate demo
preview remains available. Production deployment/load, external integrations,
every possible dataset/device and every assistive-technology combination are not
certified by these bounded checks. No claim of literal defect-free perfection is made.
