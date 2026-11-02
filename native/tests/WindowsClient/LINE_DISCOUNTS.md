# Native fixed-line-discount preservation

`DocumentLine` now uses tested `LineDiscountState` for explicit **% of line** versus **₹ fixed per line** controls. Presence of `discount_amount` (including zero) selects fixed mode on reopen, even when the API also returns `discount_percent: 0`. Serialization emits only the chosen key. Changing mode resets the prior value to zero rather than converting or accidentally combining discounts.

Quantity edits never prorate fixed discounts. New linked credit/debit returns with a positive fixed discount require an explicit review acknowledgement. Per-line identities and monotonic quantity/discount revisions invalidate that acknowledgement on edits, including change-and-change-back. Historical notes start acknowledged for their original inputs, so metadata-only changes retain their existing totals without a new gate. Conversions preserve discounts and show guidance rather than imposing the return gate. API calculation remains authoritative.

Verified locally:
- Portable state tests: preservation, zero-presence, chosen-key serialization, mode resets, no implicit proration, return review requirement/revisions and historical baseline.
- Actual isolated API through the Windows client/state: estimate `100 − ₹10` reopens, previews and saves at **90**.
- Inclusive purchase-order line `₹118 − ₹10`, GST18 included, document discount10% reopens, previews and saves at **97.20**.
- Windows semantic compilation passes. These are portable/service checks, not a claim that a Windows UI return-review journey has executed.

The opt-in local API smoke command in `COMPLETE_TRANSFERS.md` also runs these two persisted draft regression scenarios.
