# Thermal discount disclosure

Follow-up to bdec90a. Synthetic API receipts reproduced correct net totals but missing fixed/percentage line-discount, document-discount and inclusive-rate explanations in both thermal widths. The existing A4 layouts printed those details.

Both thermal layouts now print the same stored line discount label, calculated document-discount amount and inclusive-GST rate qualification. No calculation, posting or data mutation changes. Fixed and percentage inputs remain distinct; no recalculated discount is subtracted a second time.

Extended existing PDF-discount tests to both thermal widths. Baseline failed three assertions (`docs/evidence/thermal-discounts-before.log`). After the renderer change, nine targeted tests passed, including settlement/source-reference coverage (`thermal-discounts-after.log`). Scenarios include fixed INR 10, percentage discount, inclusive/exclusive GST and document discount. Existing expected totals remain INR 90.00, 97.20, 114.70 and 95.58.

Visually checked the synthetic 58mm combined-discount receipt: INR 118 inclusive rate, INR 10 line discount, INR 10.80 document discount, base 82.37, CGST 7.42, SGST 7.41, final INR 97.20. No observed clipping. Existing uneven font spacing remains a separate renderer investigation; this is not physical-printer/native or comprehensive visual acceptance. No publication or deployment.
