# Company loading and register-render assessment

This assessment uses synthetic data only. It changes no API payloads, pagination, accounting calculations, production settings or native client code.

## Demonstrated web work and fix

The web workspace retained its last complete register during a same-company refresh. Every 500-row progress notification updated React state, which reran the entire register filter and sort even though the confirmed records and filter inputs had not changed. Other unrelated workspace renders repeated the same work.

Register selection now uses component-local `useMemo`, keyed by company ID, the records array identity, register kind, search, status, all date/party/sort values and the current business date. New records, company changes, filter changes and date rollover invalidate it. The selected array is never mutated; there is no persistent or cross-company cache. Pagination and full-load readiness/error guards remain unchanged.

This reduces CPU work during refresh and unrelated renders. It does **not** reduce network latency or claim faster first-time download of a company's complete history.

## Reproducible measurement

Run from the repository root:

`node frontend/benchmarks/registerSelection.mjs`

The benchmark mounts real React components in jsdom using 30,000 synthetic invoice rows. It compares executing the same selection every render with memoized selection through 61 progress renders. Both paths must produce exactly the same ordered IDs. Row access counts are deterministic; elapsed time depends on the machine and load.

Three consecutive local runs:

| Run | Recompute every render | Component-local memo |
| --- | ---: | ---: |
| 1 | 2669.24 ms | 44.55 ms |
| 2 | 3093.42 ms | 52.39 ms |
| 3 | 2698.21 ms | 48.98 ms |

Median: 2698.21 ms versus 48.98 ms. Record-kind reads fall from 1,830,000 to 30,000, a 61-to-1 reduction. These are Node/React/jsdom CPU measurements, **not** browser paint, mobile-device or end-to-end load timings. No real-browser access was attempted for this assessment.

## Cross-platform request trace and limits

- All three clients already use compact 500-row pages and discard/retry overlapping scans rather than publish partial data. Stable full history takes `floor(N / 500) + 1` page requests, including an empty terminator at exact multiples. This patch does not change that contract.
- Android and Windows fetch records and bank accounts concurrently. No duplicate record scan was found in ordinary company selection. Their optional capability checks remain outside the critical company-data path.
- Android starts its three dashboard report requests while history loads. Windows starts them after core history has completed; reducing that waterfall would need a separate progressive-readiness change.
- Native monthly charts each scan the records once per displayed month. For 50,000 records and eight months, source analysis gives 400,000 predicate visits versus 50,000 for a potential single-pass accumulator. A separate Python algorithm proxy preserved exact Decimal totals and measured 70.70 ms versus 18.65 ms, but this is **not** Kotlin/.NET runtime evidence. No native optimization is included here.
- Android register recomposition and Windows page redraw also repeat selection work. Native toolchains were unavailable locally, so these remain measured-code-structure follow-ups, not claimed device improvements.

## Regression checks

146 web tests pass, including explicit progress-only render reuse, company/logout isolation, replacement-record invalidation, every filter/sort input, business-date rollover, master lifecycle selection and unchanged source ordering. ESLint and the production web build pass. Existing build chunk-size guidance remains unchanged. API/native behavior is unchanged; hosted CI remains the integration gate for this branch.
