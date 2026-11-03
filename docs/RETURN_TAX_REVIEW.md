# Linked return tax review

This bounded synthetic review covers API posting and report arithmetic, not tax-law certification or production records.

## Corrected: purchase returns must preserve source tax classification

A regular-GST purchase bill for ₹100 less a fixed ₹10 discount, with ₹16.20 GST marked ineligible, previously accepted a full debit note using the default pending-review classification. The payable correctly became zero, but the financial report retained ₹16.20 purchase expense and showed negative pending input CGST/SGST of ₹8.10 each. Total GST and the journal balance alone did not detect the incorrect account reversal.

Debit notes now enforce cumulative source budgets for pending CGST, SGST and IGST, plus ineligible tax. A mismatched return is rejected before posting with guidance to match the original classification. Correct explicit classifications remain supported. Missing legacy pending fields retain the same all-tax-pending fallback used by the original posting code. This does not rewrite historical records or guess which treatment the operator intended.

Synthetic tests cover both reclassification directions, omitted/default treatment, cumulative mixed-treatment returns, foreign-company source rejection, unchanged journals on rejection, full sales/purchase returns with fixed or percentage line discounts, inclusive/exclusive GST, document discounts, whole-total rounding, zero net financial/GST reports, and complete-backup restore report equality.

## Confirmed remaining limitation: independently rounded partial returns

Three separate quantity-one returns can fail to close an original quantity-three document because each return recalculates and rounds tax independently. For example, quantity 3 × ₹99.99 with an 18% rate and a 10% line discount totals ₹318.56; two unit returns of ₹106.19 leave ₹106.18, while the third recomputes to ₹106.19 and is rejected. Even without discounts, separate CGST/SGST rounding can exhaust one tax head before the other.

The existing caps fail closed rather than post excess tax. A safe correction must allocate original residual amounts to uniquely matched source lines and account for earlier returns. Simply relaxing the original amount/tax caps or silently prorating fixed discounts is not a valid correction. This limitation remains explicitly separate from the input-credit classification fix.

## Verification of classification guard

- Four focused isolated API tests pass, including the original-posting fallback for legacy bills without explicit pending-input fields.
- The aggregate suite passes: API, web unit/lint/build, local HTTP acceptance, native route-contract audit and deployment mock tests. This change does not modify native clients.
- Native device/UI execution is not claimed for this API-only guard. Existing encrypted infrastructure-backup CLI checks require `age` and were explicitly not run in this local environment; the complete-company ZIP restore regression above did run.
