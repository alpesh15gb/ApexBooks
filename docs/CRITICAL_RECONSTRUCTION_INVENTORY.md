# Critical reconstruction reconciliation — 2026-11-12

This inventory compares the surviving integrated tree with the parent thread's documented findings. It is not proof that every original lost commit was recovered. Original commit identifiers describe historical work; the local reconstructed commits are distinct. No production books were audited or changed, and no upload/deployment occurred.

## Executed reconstruction coverage

| Defect family | Surviving implementation / evidence | Status |
|---|---|---|
| Party-control manual journal divergence; server-owned payment/GST metadata; backdated notes; cancelled active-format PDF | `test_control_guards.py` | Targeted rerun passed |
| Negative-stock return reconciliation | `test_stock_reconciliation.py`, reconstructed stock restore modules | Existing synthetic evidence; incomplete replenishment/ambiguous legacy costs intentionally fail closed |
| Source-line return identity, restored references, tax/base/gross/discount residuals | `purchase_returns.py`, `test_purchase_return_lines.py`, `test_return_tax_residual.py` | Reconstructed and independently reviewed previously; fixed discounts/changed terms remain separate cases |
| Restore allocation direction, source lineage, exact target/amount, balances, stock and cancelled sources | `company_restore.py`, `restore_stock_integrity.py`; `test_restore_integrity.py`, `test_recovered_stock_restore.py`, `test_remaining_stock_restore.py` | Targeted rerun passed |
| Cancelled conversion/split-allocation trail and restore compatibility | `10c3046`, `test_record_trail.py` | Previously independently verified; no historical repair |
| Settled note chronology and original settlement dependencies | `9db279c`, `test_settled_return_lifecycle.py` | Reconstructed after 9159 candidate failure; targeted rerun and independent review passed |
| Linked-payment complete payload and normalized party retry; cash/bank POS tender | `pay_at_invoice.py`, `pos_validation.py`, `test_pay_at_invoice.py`, `test_rebuilt_pos_tender.py` | Targeted rerun passed |
| Import validation, image MIME/full decode/APNG, native CSV strict parsing | `test_rebuilt_import_images.py`, native CSV compiled suites | Image rerun passed; native parser previously compiled, full UI/device paths remain open |
| Cross-tab accepted session, logout ownership, streaming downloads, inert restoration | `6070e2a`, `d66c544`, frontend session tests | Focus/session targeted rerun passed; does not establish all native session/cache fixes |
| Period-lock/validation focus, dialog ownership | `DialogFocus`, company/period-lock tests | Eleven synthetic UI tests passed, including new nested dialog Tab/Escape/focus-return probe; no screen-reader certification |
| XLSX formula injection and identifier/error-string fidelity (historical c277a705/3db78f9 family) | New `test_rebuilt_export_text.py` and `main.py` text typing | Newly reproduced and reconstructed in this batch; three regressions failed before fix, 23 export/report tests passed after |
| PDF scope/readability and native stale share/PDF format | `41ef08e`, `5e65e6b` | Independently reviewed; full app/device acceptance remains open |

## Newly confirmed remaining gaps — release review required

1. **Party identity consistency is not fully reconstructed.** The current creation/lookup paths use SQL `lower`, whereas statements/imports use Python `casefold`. A disposable API probe created both `Straße Synthetic` and `STRASSE SYNTHETIC` with HTTP 200. ASCII space/case duplicates correctly rejected with 409. The broader historical 7c21b2b/e8b7395 behavior is therefore not present in full. Reconstruct a single company-scoped matching policy, reject ambiguous legacy matches safely, and test master/import/document/report consistency and PostgreSQL concurrency before claiming closure. Do not merge historical parties automatically.
2. **Native refresh access-denial handling is not fully reconstructed.** Source inspection of Windows `MainPage.Refresh` shows a direct `Task.WhenAll` followed by cache assignment; Android `refresh` similarly retains old cache on failed core reads. The historical e81fccc/295cc8a/3b8536c mixed-failure, core-vs-navigation and stale-navigation fixes require reconstruction and controlled tests. Source inspection here does not establish real-device behavior.
3. The full original-to-current inventory remains incomplete for all report-filter/name identity, numerical edge, authorization concurrency and platform-specific cache paths. Existing broad passing suites must not substitute for missing explicit regressions. The two reproduced candidate lifecycle blockers demonstrate why this distinction matters.

## Evidence for this batch

- 23 tests: rebuilt export text, GST exports, item activity, party ledger and party report PDF. `/tmp/apex-export-green.log`.
- 49 tests: control guards, rebuilt POS tender, linked payment, access integrity, settled-return lifecycle, image validation and three restore suites. `/tmp/apex-reconstruction-integrity.log`.
- 11 frontend tests: dialog focus, cross-tab session, company validation and period lock. `/tmp/apex-extra-accessibility.log`.
- XLSX checks inspect explicit cell types after reopening actual API response bytes. Numeric values remain numeric; barcode/HSN leading zeros, formula-like strings and Excel error literals remain unchanged text. No spreadsheet formulas were executed.

The immutable 9159 checkpoint remains unsuitable for release. Current work requires independent review, exact-SHA full CI/native builds, final browser/device acceptance and the operator-owned backup/restore/migration/writer-pause gates in `INTEGRATED_COVERAGE_MATRIX.md`. The user will deploy; no delivery date or comprehensive statutory-compliance claim is made.

## Follow-up correction

The subsequent party/native-cache batch reconstructs the two explicit gaps above; see `PARTY_IDENTITY_NATIVE_CACHE_RECONSTRUCTION.md`. The original gap descriptions are retained as reproduction history. Closure still requires independent review and native acceptance, and does not imply all historical lost changes are recovered. An additional SQLite concurrent duplicate race was reproduced and fixed with a transaction writer guard.

The next review caught incomplete Android read-cache invalidation after e46744f; the local access-cache follow-up closes the reviewed detail/PDF/statement and export boundaries. It also corrects casefold item-name stock/archive bypasses. Web revocation caches and the lost Android cash-book applied-export snapshot remain open: see `ACCESS_CACHE_ITEM_IDENTITY_FOLLOWUP.md`. Do not interpret the earlier two-gap reconstruction as closing these adjacent findings.

The web access-loss / Android pending-read batch now addresses the reviewed web detail/draft paths and stale source/edit/convert responses. The Android cash-book filter finding is corrected: it referred to dead BasicTool code, while the routed CashBookTool already used applied snapshots. The active route received cancellation/access guards and actual-body tests; see `WEB_ACCESS_ANDROID_REPORT_RECOVERY.md`. Final browser/device and independent review remain required.
