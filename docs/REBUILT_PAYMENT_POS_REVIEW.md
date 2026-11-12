# Reconstructed payment retry and POS tender safeguards

Local follow-up to 2f92720; no production access, deployment or publication.

## Confirmed defects and changes

POS preview previously accepted invalid tender strings, excess precision, non-finite numbers and excessive values. Creation rounded before validation; bank header amendments skipped the cash-only check. Shared validation now runs before rounding in preview, creation and explicit tender amendments for both cash and bank. Tender must be finite, cover the total, fit 9999999999999.99 and have at most two decimal places. Omitted creation tender defaults to total; bank change remains zero. Header edits without submitted tender retain historical metadata.

A standalone invoice's retry key could be reused at records/with-payment to append a payment. Linked operations now hash the document and complete payment terms under an operation discriminator while holding the company write lock. Exact older pair replays remain compatible only if both persisted retry hashes match; a standalone document key cannot impersonate a complete pair. Child receipt keys remain transactionally bound to their generated document ID.

Regressions fail against the preceding code and pass with these changes. Coverage includes atomic rejection, corrected retry after rejection, omitted and maximum tender, cash/bank preview-save parity, operation collision, changed payment/reference/date, exact legacy pair replay, and PostgreSQL simultaneous identical/changed requests.

## Report filters and native scope

Existing rendered tests confirm GST quarterly-to-ordinary transitions restore the ordinary date range, and switching companies clears a party selection from the old company in both UI and requests. The five accounting UI regression tests passed. No report code change was needed for these previously documented cases.

Source inspection confirms Android freezes the combined record/payment command and Windows freezes record/payment payloads for uncertain retries. This batch does not claim native device timing acceptance or reconstruct every previously lost fix.

## Evidence

- Prior-code failures: /tmp/apex-rebuilt-baseline.log.
- Seven targeted SQLite payment/POS tests passed: /tmp/apex-rebuilt-payment-pos.log.
- Five rendered accounting UI tests passed: /tmp/apex-rebuilt-report-filters.log.
- Disposable PostgreSQL evidence: /tmp/apex-postgres-rebuilt-payment; 18 concurrency tests and 76 targeted regressions passed.

Synthetic consistency checks do not establish production capacity, statutory compliance, historical repair or deployment readiness.

Final full backend suite: 337 tests passed (125.731 seconds), /tmp/apex-rebuilt-payment-full.log. PostgreSQL also passed five HTTP lifecycle tests and the eight-client workload (20 invoices, 20 partial receipts, two expenses, two credit-note returns and ten idempotent replays): zero errors; trial debits/credits both 9442.00, balance difference 0.00, stock 102 units valued at 6120.00. The owned cluster shut down cleanly.
