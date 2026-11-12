# Thermal settlement labels

Follow-up to 42d4a3b, synthetic data only. Both 58mm and 80mm note PDFs previously labelled used/refunded credit as Paid and unused credit as Balance due. Sales and purchase PDFs also labelled combined payments and return-note adjustments as Paid.

The thermal renderer now uses the existing server-calculated settlement amounts with the same distinction as the modern A4 layouts: payments received/made separately from note adjustments; credit used/refunded and credit remaining for notes. No ledger, settlement, tax, source-reference or payment allocation behavior changes.

Nine targeted tests passed: two new lifecycle cases plus source-reference and discount tests. Customer and supplier cases cover fully offset unpaid invoices, fully paid sources with untouched available credit, and partial refunds leaving INR 75 from INR 100. Both thermal widths are checked. Evidence: `docs/evidence/thermal-settlement-tests.log`.

Rendered the synthetic supplier partial-refund 58mm PDF and visually verified the INR 25 used/refunded / INR 75 remaining labels without observed clipping. Existing typography was not redesigned. No physical printer, native application, screen-reader or statutory acceptance claimed. No publication or deployment.
