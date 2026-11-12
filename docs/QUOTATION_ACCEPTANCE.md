# Synthetic nine-line quotation acceptance

The shared fixture is `native/shared/fixtures/quotation-nine-lines.json`. It contains nine goods/installation descriptions near the 200-character entry limit, nine unit types, fractional quantities, 18% GST, warranty notes and commercial terms. All identities and terms are synthetic.

Independent expected values: taxable INR 14,732.73, CGST INR 1,325.95, SGST INR 1,325.95, round-off +INR 0.37, total INR 17,385.00. The quotation must have no journal posting; conversion creates one linked invoice and a second conversion is rejected atomically.

The backend regression checks preview/save/conversion, exact descriptions and units, warranty/terms and every A4 PDF layout for both quotation and invoice. It verifies final-line sentinels survive pagination, the grand total shares a page with its tax breakdown, and unlike units are not combined into one total quantity. Optional `APEX_QUOTATION_PDF_EVIDENCE` saves the synthetic PDFs for rendering. Production data is not needed.

The scenario exposed omitted units in most PDF layouts, narrow unit wrapping in Evergreen, and a legacy total split across pages. Units now also appear under each description in every A4 layout, mixed-unit documents show item count rather than summed quantity, and legacy totals stay together. System Poppler is used for visual review; the workspace's bundled Poppler had a font-substitution rendering problem, so it was not used to judge final typography.

`run_local.py --browser-only --business` now includes real browser entry of all nine rows, server preview, quote PDF download and invoice conversion. The web component regression also checks exact submitted fields on reopen/conversion. Windows UI smoke uses an API-seeded quotation, reopens and saves it through the real native form, then converts it and verifies all canonical fields and calculated totals. Android unit tests exercise actual LineState serialization/reopen for all nine rows. The latter does not establish Android device entry, screen layout or PDF viewer behavior.

Keep CI/build checks, hosted Windows UI evidence, Android unit-state coverage, and physical-device acceptance distinct. Further Android device entry/conversion/PDF acceptance remains required. These synthetic workflows do not validate legal GST applicability, warranty terms, invoicing eligibility or filing obligations.
