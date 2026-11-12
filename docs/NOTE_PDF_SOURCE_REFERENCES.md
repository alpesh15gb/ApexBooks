# Note PDF source references

Local follow-up to cce97c5; no publication or deployment. This changes presentation only, with no migration or book mutation.

Credit-note exports now show the stored original sales-invoice/POS number and date. Purchase-return debit notes show the linked purchase bill's **book reference** and date, with a statement that this is a purchase return in these books, not a supplier-issued GST debit note. The application does not independently verify the supplier's external invoice identity. References are resolved by source ID, expected kind and company at export time; submitted display metadata is ignored. Missing numbers are not replaced with UUIDs. Unlinked, missing/foreign/wrong-kind and cancelled historical sources receive qualified text. Cancelled notes themselves retain the existing blocked-export policy.

All nine A4 and both thermal layouts render the same server-resolved text above the item table. The association survives identifier remapping on restore. This does not introduce multi-invoice notes, infer missing references, certify a GST document, alter tax eligibility, or repair historical books.

## Official-source assessment

Read on 2026-11-12:

- [CBIC invoice rules page](https://cbic-gst.gov.in/gst-invoice-rules.html) includes corresponding invoice particulars. Its numbering/content is historical and is not relied upon as a complete current consolidation.
- [GST Council-hosted CBEC credit-note flyer](https://gstcouncil.gov.in/sites/default/files/e-version-gst-flyers/Credit%20Note%20under%20GST.pdf), format section, includes corresponding invoice/bill number and date for a supplier credit note. Other portions contain historical time limits; this is not current filing guidance.
- [CBIC Rule 53 active repository](https://taxinformation.cbic.gov.in/content/html/tax_repository/gst/rules/cgst_rules/active/chapter6/rule53_v1.00.html) and the official 2021 consolidated PDF timed out during retrieval. Current legal applicability remains a separate verification gate. Council recommendations, invoice reporting delinking and post-sale discount changes must not be assumed to remove document particulars or equated with an enacted rule without checking the operative instrument.

The factual linked-reference improvement is justified by product traceability independently of statutory applicability. A buyer's purchase-return debit note must not be presented as proof of a supplier-issued section 34 debit note.

## Evidence

`docs/evidence/note-pdf-source-tests.log`: 14 targeted tests passed (five new source-PDF cases plus existing discounts, quotation and document-trail suites). Covers all 11 templates, regular intra-state GST and unregistered books, POS sources, submitted display spoofing, no export mutation, two repeated restores for customer/supplier notes, missing/foreign/wrong-kind references, missing number, cancelled source, cancelled-note export refusal, escaped long references and preserved ending text.

44 synthetic PDFs generated in `/workspace/shared/apex-note-pdf-source`. Visually inspected first pages of purchase-return Evergreen, purchase-return 58mm thermal, and long-reference classic credit note. Reference/date and wrapping are visible without observed clipping. This is sampled visual review, not every-page/device/print or tagged-PDF accessibility acceptance. Existing typography and thermal settlement labels were not redesigned. No real business data used.
