# Reconstructed percentage-discount return fix

The former local commit c1a2d4d was unavailable after workspace replacement. This is a newly implemented and retested change based on published PR #56 (9b21ccce016592caf155b14d363475eb7bdce050), not recovery of its exact bytes or history.

Reproduction: purchase three units at INR 0.13 inclusive of 18% GST with 10% document discount. Source total is INR 0.35. Three one-unit returns independently calculate INR 0.12 each; the published base rejects the last return with 422. The regression fails on that base and passes here.

For an unambiguous source line with unchanged price, inclusive flag, percentage discounts and prior return terms, allocate cumulative source gross by returned quantity. Allocate base/tax within that gross using existing component budgets. Reflect the paise difference in the line's document-discount amount. Quantity, source value and tax caps remain enforced. Changes beyond one paise or a negative discount fail closed. Fixed-amount discounts, changed prices and ambiguous historical allocation do not opt into this calculation. Existing books are not rewritten.

Validation: nine return-residual API tests, including fractional splits, both ITC classes, preview/save agreement, amount/discount consistency, amendments and capacity caps. The complete backend run and final commit IDs are recorded in the review PR. SQLite tests are not PostgreSQL concurrency or device acceptance; this is not a statutory-compliance or production-readiness claim.

## Independent-review follow-up

Two additional unchanged-term cases were reproduced: 3 × INR 0.37 with 7% line discount and no document discount; and 3 × INR 0.03 with 7% line discount plus 5% document discount. Allocate each discount component cumulatively against its own source budget; do not force line-discount residuals into document discount. Reconstruct before-discount gross from the allocated net and discounts, capped at a one-paise price adjustment. For verified unchanged terms, the combined base/tax rounding guard permits two paise; changed/fixed-price paths retain their original one-paise guard. Quantity, source gross/base/tax caps remain strict. Regressions verify full component sums, preview/save equality and rejection after source quantity exhaustion. Both new cases failed closed before the follow-up; no over-refund was reproduced.
