# Inward workbook tax allocation

## Confirmed discrepancy

Two purchase or expense lines of INR 0.06 at 18% GST each save INR 0.01 line tax. With one line marked pending input-credit review and the other ineligible, the saved document and ledger correctly contain INR 0.01 pending credit and INR 0.01 cost/ineligible tax. The inward XLSX export independently rounded both CGST and SGST onto the first line, then inferred eligibility from that inflated line allocation. Its summary incorrectly showed INR 0.02 proposed credit and zero ineligible tax.

This is a book-derived export discrepancy, not a change in legal tax eligibility or a portal filing. The correction must retain saved tax classification and reconcile line, document and report amounts without changing accounting entries. Outward exports are outside this change.

## Corrected behavior

An inward-only allocator uses the saved pending-review tax-head budgets and their saved ineligible remainder. Allocation conserves each consistent line's tax, each head and each classification bucket in whole paise; it never independently rounds two heads past a line's tax. Large supported amounts use integer-cent ratios to avoid decimal-context multiplication precision loss. The outward allocator is unchanged.

Legacy documents without pending fields retain the existing API fallback to the saved tax heads, not newly inferred eligibility. Where line weights do not reconcile with saved classification, original taxable rows remain and explicitly labelled zero-taxable-value document reconciliation rows carry the saved tax budgets. These rows say they are not invoice items and require source review. Negative, fractional-paise or internally impossible saved budgets return a controlled review-required conflict rather than creating new credit. This can also block inward report preparation for inconsistent legacy records; it does not rewrite or repair those records automatically.

## Verification boundary

Fourteen focused tests (five new and nine existing export tests) passed. Actual XLSX/API/ledger comparisons cover both line orders, intrastate/interstate purchases and expenses, returns, tenant isolation and both JSON/ZIP restore formats. Additional tests cover odd-paise row/head/bucket margins, large values, legacy defaults, explicit reconciliation rows and controlled invalid-budget rejection. Independent randomized review of 10,000 mixed-bucket cases found no margin or nonnegative-allocation discrepancy.

Full local aggregate passed: 272 backend tests; 169 web tests, lint and production build; five isolated HTTP workflow tests; a 6,402,964-byte complete-backup roundtrip in 13 bounded chunks with archived evidence hashes preserved; 232 matched native API routes; nine backup-target and 21 management mock tests plus simulated backup/restore safety checks. The encrypted infrastructure-backup CLI check was not run because `age` and `age-keygen` are unavailable. Hosted CI, including PostgreSQL and native builds, remains the next immutable-checkpoint gate. No main, production, tax filing, native-device or browser actions are involved. This remains a provisional book-derived workbook, not a portal GSTR-2A, filing or tax-eligibility certification.
