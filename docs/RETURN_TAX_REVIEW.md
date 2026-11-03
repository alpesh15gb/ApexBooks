# Linked return tax review

This bounded synthetic review covers API posting and report arithmetic, not tax-law certification or production records.

## Corrected: purchase returns must preserve source tax classification

A regular-GST purchase bill for ₹100 less a fixed ₹10 discount, with ₹16.20 GST marked ineligible, previously accepted a full debit note using the default pending-review classification. The payable correctly became zero, but the financial report retained ₹16.20 purchase expense and showed negative pending input CGST/SGST of ₹8.10 each. Total GST and the journal balance alone did not detect the incorrect account reversal.

Debit notes now enforce cumulative source budgets for pending CGST, SGST and IGST, plus ineligible tax. A mismatched return is rejected before posting with guidance to match the original classification. Correct explicit classifications remain supported. Missing legacy pending fields retain the same all-tax-pending fallback used by the original posting code. This does not rewrite historical records or guess which treatment the operator intended.

Synthetic tests cover both reclassification directions, omitted/default treatment, cumulative mixed-treatment returns, foreign-company source rejection, unchanged journals on rejection, full sales/purchase returns with fixed or percentage line discounts, inclusive/exclusive GST, document discounts, whole-total rounding, zero net financial/GST reports, and complete-backup restore report equality.

## Corrected for unambiguous single-line sources: final partial-return rounding

Three separate quantity-one returns can fail to close an original quantity-three document because each return recalculates and rounds tax independently. For example, quantity 3 × ₹99.99 with an 18% rate and a 10% line discount totals ₹318.56; two unit returns of ₹106.19 leave ₹106.18, while the third recomputes to ₹106.19 and is rejected. Even without discounts, separate CGST/SGST rounding can exhaust one tax head before the other.

The follow-up reconciles only the final return of a one-line source when all earlier notes have the same economic inputs, their stored calculations can be reproduced exactly, and cumulative quantities equal the source quantity. Fixed discounts must have been explicitly allocated proportionally within one cent and add back to the original fixed discount exactly. The server does not change entered discounts, rates or quantities.

The final calculated base, tax heads, supply classification and pending/ineligible input-tax amounts use the original values less prior notes. Every change must fit a conservative rounding bound of one cent per return, with at most 100 prior notes. Normal amount, tax and stock limits still apply afterward. Server-only `return_rounding` metadata records before/after values and source lineage; client-supplied reconciliation metadata is ignored.

Canonical preview uses the same calculation. All clients pass the linked source; existing-return previews also pass a tenant-validated `preview_record_id` so the current note is not counted twice. The preview identifier is not saved as accounting data. Header-only amendments preserve the exact posted values.

Ambiguous/multiline sources, changed prices or tax classifications, mismatched fixed discounts, whole-rupee total rounding, unverified historical calculations and other ineligible cases retain existing fail-closed limits. This is not a general automatic proration engine and does not repair historical postings.

## Verification of classification guard

- Four focused isolated API tests pass, including the original-posting fallback for legacy bills without explicit pending-input fields.
- The aggregate suite passes: API, web unit/lint/build, local HTTP acceptance, native route-contract audit and deployment mock tests. This change does not modify native clients.
- Native device/UI execution is not claimed for this API-only guard. Existing encrypted infrastructure-backup CLI checks require `age` and were explicitly not run in this local environment; the complete-company ZIP restore regression above did run.

## Verification of residual reconciliation

Ten focused backend tests cover both credit/debit directions, fixed/percentage/document discounts, inclusive/exclusive and interstate GST, ineligible purchase tax, exact retry, foreign and mismatched preview IDs, header amendments, complete-backup restore, and actual tracked-sales quantity/cost restoration. Changed economics, excessive/nonproportional fixed discounts, ambiguous lines and excessive prior-note counts do not authorize reconciliation. A web hook test verifies linked-source/edit identity forwarding and use of the canonical amount.

An independent read-only synthetic review found no concrete discrepancy or cap bypass in this bounded logic; inclusive sales and purchase GST/ITC totals netted to zero after full return. This is not a general audit certification.

Native preview-only forwarding tests are authored separately. Their compilation and runtime verification require hosted CI because the local native toolchains are unavailable; no new Android device permission or test run is implied.

The final local aggregate passes 214 backend tests, web tests/lint/production build, local HTTP checks, 232 native route literals with zero unmatched routes, and 9 backup-target plus 21 deployment mock tests. Three Android preview tests and seven Windows preview assertions are authored but await hosted native compilation. Main and production are unchanged by this review branch.
