# Staggered subset returns: accounting limits

This synthetic assessment does not change posting behavior. Returns outside the bounded final full-line-set reconciliation continue through ordinary amount, quantity, tax-head and input-tax classification checks. A failed request must leave books unchanged.

## A source line does not always have a uniquely identifiable tax-head budget

Persisted document lines contain total GST. CGST and SGST are stored at document level, with pending-input heads also stored at document level. Consider two distinct pending-review lines, each with taxable value 0.06 and GST 0.01. The source has total CGST 0.01 and SGST 0.01. Both allocations fit every saved value:

- First line CGST 0.01, second line SGST 0.01.
- First line SGST 0.01, second line CGST 0.01.

Choosing one by line position would invent an allocation not established by the persisted source. Reordering does not resolve that ambiguity. The current implementation does not make that choice.

## Some narrow subsets have a unique arithmetic answer

For a source with exactly one pending-review taxable line and a separate ineligible line, saved pending-input heads identify the first line's whole tax group. In the tested case, its source CGST and SGST are 14.49 each. The first half return consumes 7.25 CGST and 7.24 SGST. Completing that group would uniquely require 7.24 CGST and 7.25 SGST, leaving the ineligible group's 7.32/7.32 unchanged.

An IGST-only source also avoids the two-head allocation ambiguity: a line's saved tax is its IGST. These observations establish arithmetic feasibility, not a completed implementation or permission to change previously posted values.

## History can make a seemingly valid correction impossible

A tested history leaves total remaining CGST at zero while remaining pending-input CGST is 0.01. That pending amount cannot be returned without exceeding the total tax-head budget or modifying earlier classifications. The request must remain rejected.

## Why this pass retains fail-closed behavior

After reconciling one subgroup, its adjusted values may no longer equal an independent canonical recalculation. Later returns must still distinguish a valid prior adjustment from altered or unverifiable history. Trusting a submitted or imported reconciliation marker is not sufficient. Supporting successive subgroup adjustments requires a separately verified history mechanism, including bounded prior identities, dependency validation, restoration and concurrent-posting behavior.

The existing full-line-set correction avoids that continuation problem by adjusting only the final exhaustion of the complete source. This assessment does not relax its rules, silently prorate fixed discounts, rewrite history or add an arbitrary tax-head tie-break. No production data, real company backup or external tax-filing service is used.
