# Reconstructed percentage-discount return fix

The former local commit c1a2d4d was unavailable after workspace replacement. This is a newly implemented and retested change based on published PR #56 (9b21ccce016592caf155b14d363475eb7bdce050), not recovery of its exact bytes or history.

Reproduction: purchase three units at INR 0.13 inclusive of 18% GST with 10% document discount. Source total is INR 0.35. Three one-unit returns independently calculate INR 0.12 each; the published base rejects the last return with 422. The regression fails on that base and passes here.

For an unambiguous source line with unchanged price, inclusive flag, percentage discounts and prior return terms, allocate cumulative source gross by returned quantity. Allocate base/tax within that gross using existing component budgets. Reflect the paise difference in the line's document-discount amount. Quantity, source value and tax caps remain enforced. Changes beyond one paise or a negative discount fail closed. Fixed-amount discounts, changed prices and ambiguous historical allocation do not opt into this calculation. Existing books are not rewritten.

Validation: nine return-residual API tests, including fractional splits, both ITC classes, preview/save agreement, amount/discount consistency, amendments and capacity caps. The complete backend run and final commit IDs are recorded in the review PR. SQLite tests are not PostgreSQL concurrency or device acceptance; this is not a statutory-compliance or production-readiness claim.
