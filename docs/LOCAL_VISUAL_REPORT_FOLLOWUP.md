# Local visual audit follow-up: reports, navigation and validation

## Implemented

- Reorder confirmation (a024730): successful PO draft save records a company-scoped confirmation before list refresh, with an Open purchase order action. The in-app worklist Refresh retains it; browser reload persistence is not implemented. Low-stock alerts stay visible. No confirmed incoming-stock quantity is inferred from drafts.
- Day book: discover all journals without a current document posting, including noncash and zero-net manual entries. Display debit/credit totals, preserve cash/bank movement totals and avoid duplicating linked document journals. Cancellation labels require actual reversal lineage and a cancelled source, not just an AUTO-like reference. Tests cover date isolation, restore, document deduplication and reference lookalikes.
- Item activity: retained API quantity keys for compatibility but explicitly identify the basis as purchase/sales documents only. Web and XLSX/PDF replace opening/closing stock language with net document movement. The reproduced introduction 10, adjustment -5, purchase 7, sale -1 yields document net 6 and tracked stock 11; tests distinguish these correctly.
- Report controls wrap with usable date/period widths. At short/high-zoom viewports, the whole navigation drawer scrolls instead of its nav collapsing. Browser acceptance cases cover party-report control geometry and 320x200/303x199 drawer navigation; these cases have not run in this restricted execution environment.
- Party statement copy now acknowledges posted opening balances and settlements while retaining the text-name matching caveat.
- Company GSTIN/state mismatch is actionable, role=alert, linked through aria-describedby and aria-invalid to both fields, and focuses State code. Correcting the input clears the stale error. Server validation remains authoritative.

## Evidence and boundaries

Before final item-report/copy additions: 342 full backend tests, 181 final frontend tests, lint/build, 18 PostgreSQL concurrency tests, 82 PostgreSQL regressions, five HTTP lifecycle tests and a zero-error accounting workload. Item-report scope/XLSX/PDF plus Day book targeted suite: four tests passed. Rendered company/report/reorder checks: 21 passed. Final integrated backend result is recorded in the handoff.

Working browser acceptance belongs to the isolated desktop reviewer and must use the integrated revision. This execution environment cannot start Chromium because its required socket is blocked. Production was not accessed or deployed.

## Next high-priority findings

- Invoice/payment trail must include linked credit/debit notes, allocations and relevant refunds, with authorized backlinks and cancellation status.
- Repeat partial sales returns should show reliable remaining per-line allowances and default quantities without weakening source, discount, tax or server caps.
- Journal history voucher metadata/source links, stock-specific detail presentation and a server-calculated invoice totals bridge remain follow-up UX tasks.

Final integrated local verification: 343 backend tests passed in 110.830 seconds (/tmp/apex-report-integrated-backend.log); 181 frontend tests passed (/tmp/apex-report-integrated-frontend.log), lint passed and build budgets passed. PostgreSQL evidence for the Day book changes: /tmp/apex-postgres-daybook. Real-browser drawer/filter scenarios remain unexecuted here; Python syntax checks alone are not visual acceptance.
