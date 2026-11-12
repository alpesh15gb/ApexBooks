# Negative-stock returns and historical review

## Implemented behavior

Normal inventory valuation remains moving average. For a sale made with insufficient stock, later incoming stock settles outstanding shortages in transaction order, FIFO between sales. The return records evidence of the receipts and the allocated cost differences. This is a deterministic application policy, not a claim of statutory acceptance for every business.

The reproduced sequence (sell 5 from zero, purchase 5 at ₹60, return all 5) now leaves 5 units and ₹300 in inventory, with zero remaining purchase expense from those units. A return reverses the purchase-price variance in the purchase-expense account and the original sale cost in COGS. It does not amend the original sale or replenishment journals. Partial returns allocate source cost proportionally; remaining cents are capped and exhausted on the final return. Physical ecommerce receipts use the same valuation and posting rules.

A source's shortage must be fully replenished before its physical return can be valued. Incomplete source costing, unvalued movements, ambiguous same-day transaction order, unsupported historical deficit receipts, and earlier unreconciled provisional-cost returns fail closed. Financial-only credits remain possible under their existing rules. The application does not repair historical records automatically.

## Read-only historical audit and reconciliation plan

1. Capture the exact production revision, schema version and a consistent, tenant-scoped export plus database backup. Record hashes and extraction time. Verify restore in an isolated environment with outbound integrations and workers disabled. Never point a review script at a writable production connection.
2. Preserve the original export. Work from an immutable copy; run structural backup validation first. Record orphan links, unbalanced journals, missing valuation and duplicate identities as separate blockers rather than silently fixing them.
3. For each item, reconcile summed stock movement cost to the inventory control account, by reporting date and financial period. Flag nonzero value on zero quantity, positive value on negative quantity, missing source lines, and missing/duplicate same-day creation times. Identify provisional sales and subsequent receipts; list unresolved quantities and any old physical returns lacking reconciliation evidence. Replay the proposed allocation only in memory and compare it with recorded values. Do not assume current balances prove every historical period was correct.
4. For each party-control account (AR, AP, customer/supplier credits and advances), enumerate manual journal lines and imported opening entries, excluding neither reversals nor offsets from review. Reconcile GL, party statement, ageing and allocation totals at each affected cutoff. Inspect client-supplied derived payment credit fields, advance classification on ordinary invoices, backdated notes before settlements, cancelled documents with surviving allocations, and cross-party allocations. Distinguish legitimate verified imports from unexplained differences.
5. For each supplier return, trace original purchase lines, quantities, taxable values, tax components and ITC treatment. Compare cumulative posted reversals to their source by line and tax component. Flag ambiguous mixed-treatment lines and older defaulted treatment; do not infer entitlement from a mathematically balanced journal. Reconcile affected GST report schedules separately, including cancelled documents and advance metadata.
6. Produce a per-company exception register: source IDs, dates, recorded/proposed amounts, affected periods/reports, reproducible calculation, uncertainty and supporting evidence. Have the book owner/accountant approve the economic treatment and any filing consequences. A lack of exceptions in these checks is not a compliance certificate.
7. Prepare corrections as separately reviewable entries or an explicitly approved migration, with a before/after report and rollback drill. Preserve audit history and locked periods. Run against a restored copy first. Production correction requires verified backup, restore, migration, writer/worker pause and recovery procedures; this change does not authorize or execute historical repair.

No live historical audit was run for this batch; the above is the execution and evidence plan.

## Safe source-line selection: design and follow-up

The current mixed-treatment purchase-return safeguard rejects ambiguity. Replace guesswork with explicit source-line identity across API, web, Windows and Android:

- Give source document lines immutable server-owned identities. For legacy documents, derive an identity from source document ID plus original index and a server-owned snapshot/version; do not use a user-editable description as identity. Do not reorder or replace a source line after it has dependent returns.
- Return editors select the posted source first, then show source line number, item/description, remaining quantity/value, GST rate and recorded ITC treatment. Send the selected identity and source version. Reject stale selection, wrong company/document, mismatched item, or a cancelled source atomically. Preserve the identity in preview, save, reopen and amendment paths on every client.
- Derive ITC treatment and tax classification from that source line. Bound cumulative returned quantity, taxable value, tax components and input-tax reversal by the selected source line, including financial-only notes and multiple rows in one request. Use remaining-value residuals for rounding. Existing document-level caps remain additional guards.
- Older returns without line identity require unambiguous matching or manual review before new per-line allocations; do not allocate them arbitrarily. Repeated same-item lines with different discounts, rates or treatment must remain distinct.
- Required regressions: identical descriptions/items with different treatment, partial and full mixed returns, repeated selection in one request, concurrent requests, cancelled/amended returns, stale source revisions, spoofed identities, cross-company references, rounding, preview/save parity and native/web reopen behavior.

The stock reconciliation batch did not implement this workflow. The subsequent source-line batch implements a source-local index plus financial fingerprint and conservative legacy allocation checks; see `PURCHASE_RETURN_SOURCE_LINES.md` for the actual contract and remaining limitations.
