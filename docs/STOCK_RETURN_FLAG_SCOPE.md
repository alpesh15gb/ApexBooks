# Stock-return option scope

## Confirmed defect

A tracked purchase bill for 10 units at INR 5 with `return_stock: false` posted INR 50 to inventory but omitted the stock movement. Stock reports therefore showed zero quantity/value and a subsequent sale failed for insufficient stock. The same irrelevant option on a sale or POS receipt posted cost of goods sold and reduced inventory in the ledger without reducing physical stock. Item-activity reports also incorrectly zeroed these normal document quantities.

## Correction boundaries

The stock-return option belongs only to credit/debit notes. Normal purchases, sales and POS postings ignore and remove this irrelevant input, including when carried forward by a draft/conversion or financial amendment. The movement writer and item-activity report apply the option only to actual return notes. Existing financial-only returns remain unchanged.

No historical records, journals or missing movements are automatically rewritten. Item-activity reports describe normal document quantities even if an older row retained the irrelevant option; that is not a repair of its historical stock subledger. A header-only amendment does not secretly repair accounting history. Any explicit financial correction still follows existing validation and reversal/repost rules.

No schema, tax eligibility, client capability, main, live data, device or browser change is involved.

## Verification

Five new focused tests and 19 related stock/return tests passed. They cover irrelevant flag values on normal purchases/sales/POS, missing/true/false choices on actual returns, exact retries, item reports, JSON/ZIP restore, historical header-only versus explicit financial amendments, differing purchase costs, adjustments and backdate rejection. Independent review reran the five regressions successfully.

An independent synthetic historical-shortage probe reconciled stock value with inventory GL at ten historical boundaries: marked opening shortage -2/value0, successive replenishment with explicit shortage costs, mixed-cost purchases, sales, partial customer returns, supplier return and write-off. Both legacy JSON and complete ZIP preserve the initial marked negative state and final positive inventory. Exact retries and rejected backdates leave journals unchanged. These are synthetic source-marked cases, not a claim that every historical source inconsistency is repaired.

Full local aggregate passed: 280 backend tests; 169 web tests, lint and production build; five isolated HTTP tests; a 6,402,960-byte complete-backup roundtrip in 13 bounded chunks retaining archived evidence hashes; 232 matched native API routes; nine backup-target and 21 deployment-management mock tests plus simulated backup/restore safety checks. The encrypted infrastructure-backup CLI check was not run because `age` and `age-keygen` are unavailable. Hosted CI is still required for this immutable checkpoint. No user backup is modified.
