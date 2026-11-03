# Purchase-return preview and posting parity

## Demonstrated issue

A purchase bill with an ineligible GST line totaling 106.20 could be copied into a debit note, changed to input GST pending review, and still preview successfully at 106.20. Posting correctly rejected that change because the original bill had no remaining pending-review classification budget. The preview therefore looked valid when the same request could not be posted.

Preview and posting now share the existing cumulative document-amount, tax-head and purchase input-tax classification caps. A classification mismatch returns the same 422 before posting. This does not automatically reclassify a line, claim input credit or change the underlying posting rules. A preview is advisory: another client can consume the remaining budget before Save, which must still validate under its transaction lock.

For a verified existing posted note, an unchanged financial signature preserves the original posted totals and classifications during a nonfinancial edit, matching the amendment endpoint. This includes historical notes that predate current budget enforcement. Changing financial inputs remains subject to the caps; supplying an existing note ID cannot exempt a new note from posting validation.

The web return editor displays the source bill's stored classifications outside collapsed line options and explains that earlier returns reduce the remaining classification budget. Missing historical classifications are described as unspecified, not inferred as eligible. User edits remain explicit. Copied fixed rupee discounts are not automatically prorated; the existing review acknowledgement remains required for changed returned quantities.

## Verification and limits

Synthetic tests cover both classification directions, mixed classifications, cumulative partial returns, existing-note self-exclusion, unchanged historical notes, changed financial inputs, legacy pending-field fallback and cross-company source rejection. UI-derived payload checks confirm that the invalid change now previews and posts with 422 without journal changes. Explicitly reviewed half quantities and fixed discounts preview and post at 53.10 each.

The existing single-line final-return residual correction is not expanded here. Certain mixed, multi-line tax-inclusive partial-return splits can still exceed a tax-head budget by a paise. They now fail consistently at preview and Save rather than displaying a misleading valid preview; no guessed residual allocation is applied.

No schema migration, new capability, native client payload change or production data rewrite is required. Previously accepted over-budget preview requests now return 422. No real-browser or new device test is claimed for this change; the web checks use synthetic component/API tests. Actual statutory input-credit eligibility and filing remain outside this correction.
