# Cumulative original-cost allocation for stock returns

## Reproduced reconciliation error

A synthetic tracked purchase acquired six units for total inventory cost 0.03. After all six units were sold, six separate one-unit customer returns restored the original sale's cost. The old per-return calculation rounded each partial cost independently to 0.01. Five returns therefore restored 0.05, and the last used a negative residual of -0.02.

The stock report ended at quantity 6 and value 0.03, while the inventory ledger showed 0.05: negative inventory/COGS posting entries were omitted by the posting builder. A balanced trial balance alone did not reveal this stock-to-ledger discrepancy.

## Correction scope

Allocate original sale cost cumulatively at the cumulative returned quantity, subtracting the cost already returned. A final complete return receives the exact remaining original cost. Never emit a negative return cost or exceed the source's total cost. Multiple lines for the same item in one request participate in the same cumulative budget.

This applies to linked customer credit-note stock returns and separately received ecommerce physical returns. It does not change invoice prices, taxes, financial credit amounts, purchase-return moving-average valuation or the user's reviewed quantities. Tax rounding remains a separate calculation.

A legitimate physical return can have zero monetary cost. Such a return still consumes physical quantity and has a stock movement even when no journal is needed. Later return budgets must include movement-backed physical return records, not only records with a journal posting.

## Historical and operational limits

No prior records or journals are rewritten. Historical return cost already exceeding the source cost fails closed and requires explicit reconciliation; the system must not manufacture a negative final receipt to hide the difference. Prior valid cent rounding may temporarily exceed the new cumulative target while remaining within total source cost; subsequent allocations cannot reverse that prior cost and must remain nonnegative.

This change is isolated development using synthetic data. It is not a historical-data repair, production migration, permission grant or claim of universal stock correctness. A separately reproduced inability to write off valid zero-valued stock via manual adjustment is outside this patch.

## Verification checkpoint (2026-11-03)

The full isolated backend suite passed 236 tests; the focused stock/commerce/tax-return selection passed 31. New cases cover six partial returns with complete ZIP restore, repeated same-item lines, concurrent halves and same-key replay, inconsistent historical cost rejection, valid historical rounding catch-up, ecommerce zero-cost physical receipts and mixed physical/normal quantity caps. Independent review passed the six new tests and 10,000 deterministic random full-return partitions, checking nonnegative allocations, remaining-cost bounds and exact final cost.

Five existing HTTP journeys and the 6.4 MB complete-backup HTTP round trip also passed. A dedicated PostgreSQL concurrent half-return regression was added and syntax-checked, but local PostgreSQL was unavailable; execution awaits hosted CI. No client code, schema, API contract or device workflow changed. Existing native/device verification is not represented as a new stock-return UI test.
