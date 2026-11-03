# Bounded final-return rounding for multiple lines

## Scope

Repeated partial returns can round GST heads differently from the original document. A final economically identical return may exceed a saved tax-head cap by a paise even though the quantities and total discount inputs exhaust the source correctly.

The correction is deliberately restricted to a final return of the complete source line set:

- The source has 2–100 uniquely identifiable lines, and every previous and current note contains that same signature set. Line order may differ.
- Identity includes the item/description/HSN/unit and financial terms: rate, GST rate, discount mode and percentage, inclusive-tax basis, tax treatment and input-tax classification. Duplicate or changed signatures do not qualify.
- Cumulative returned quantities exactly exhaust every source line. Explicit fixed-discount inputs already sum to the source discount and meet the proportional tolerance. No discount input is generated or prorated automatically.
- Source and earlier notes have canonical, verifiable calculated values. Header tax context and percentage discount remain unchanged; additional charges and whole-document rounding are excluded.
- Remaining line and header calculated values must be nonnegative, within the bounded rounding tolerance and mutually consistent. Line gross less discounts, taxable categories, tax totals and pending/ineligible input-tax allocations must reconcile.

Only derived final-note values are reconciled to the remaining source amounts. The normal amount, tax, classification, quantity and stock checks still apply. Preview and posting use the same calculation; the transaction must recheck on Save because another client may post first. Existing posted records are never rewritten.

## Deliberate exclusions

This is not a general allocation algorithm for arbitrary partial returns. Returning only a subset of source lines while leaving other lines untouched remains outside this correction, including cases where one selected line is fully exhausted. Ambiguous duplicate lines, changed economics or classifications, unverified historical calculations and prior display edits that break the strict identity match retain ordinary validation. A full-set case also remains rejected if previous postings already consumed a tax head needed by the remaining input-tax classification: correcting that would require changing recorded history. Some of these cases can still return 422 at a paise cap. The system does not guess a line identity from row position or silently reclassify tax.

There is no claim of tax-filing certification, automatic discount proration or correction of historical documents. No production data or supplied company backup is used in the synthetic review.

## Synthetic verification

Focused tests cover credit/debit notes, reordered lines, inclusive/exclusive tax, explicit fixed and percentage discounts, repeated splits, tracked-stock and inventory-ledger reconciliation, exact retry and portable restore. Negative cases retain ordinary validation for duplicate or missing identities, changed economics and unverifiable history. A PostgreSQL concurrent final-return test is included for hosted execution.

An independent 24-case matrix covered 2–5 lines, sales and purchase sources, intra-state and inter-state tax, mixed price bases, fixed/percentage discounts and a 3.25% header discount. All cases conserved source amount, every derived line field, tax heads and input-tax buckets; preview matched posting and retries did not duplicate the books. A complete ZIP copy retained the reconciled results. These are synthetic accounting checks, not production capacity or statutory filing evidence.
