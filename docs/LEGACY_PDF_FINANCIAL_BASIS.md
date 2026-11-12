# Legacy A4 financial presentation

Follow-up to 4e4d55f. Classic/Compact/Bold/Minimal use a separate renderer. Synthetic tests reproduced a fully returned unpaid invoice displaying Amount paid INR 100 despite zero payment, plus missing combined document-discount disclosure. The previous Gross value subtotal reconstruction mixed calculated taxable value with line discounts and omitted document discounts/inclusive-price treatment.

The renderer now prints stored per-line document-discount amounts and inclusive-rate qualification. Totals start from the stored subtotal after discounts, then tax/charges/rounding and total; no invented gross reconstruction. The existing line-discount column retains fixed-vs-percentage inputs. Invoice payments and note adjustments are separate; return notes show used/refunded and remaining credit using the existing server credit calculation. No accounting or data mutation changes.

Baseline: two failures in `docs/evidence/legacy-pdf-basis-before.log`. Final: 12 targeted tests passed in `legacy-pdf-basis-after.log`, covering all legacy layouts, customer/supplier offsets and unused credit, fixed/percentage and inclusive/exclusive discount cases, source/restore/font checks and 18 quotation/invoice PDFs. Visually checked Classic supplier credit with INR 0 used and INR 100 remaining; no observed clipping. Physical printer/device and complete visual acceptance remain open.

The separate confirmed Hindi/Gujarati missing-glyph problem is not solved by this change. Current DejaVu embedding is not multilingual readiness. No publication or deployment.
