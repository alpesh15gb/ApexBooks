# Zero-value physical stock adjustments

## Scope

A tracked item can legitimately have quantity with zero inventory value, for example a fully discounted sample on an otherwise payable purchase bill. Previously, writing off that quantity failed because the adjustment endpoint required a positive financial amount.

The adjustment endpoint now records a nonzero physical quantity change when its calculated value rounds to zero. It creates an immutable adjustment record, stock movement and audit event, but no journal or record-posting link. Its response and idempotent replay both return `posted: false`: this describes the financial journal status, not an editable draft or an unapplied stock change.

Positive-value adjustments continue to post their existing balanced inventory gain/loss journals. Quantity must remain strictly positive. Explicit zero or negative unit cost for an increase is still rejected; accepted positive unit costs can produce a zero amount after normal cent rounding. Decreases still reject a supplied unit cost and use the existing moving-average calculation. No inventory is silently revalued.

## Safety and recovery

Existing company write authorization, tracked-item ownership, period locks, backdating restrictions, reservation checks, unknown-cost rejection and company transaction serialization still apply. Zero-value movements cannot be edited through generic draft or document routes. Retrying the same successful command returns the same record without another movement or audit event; changing its body under the same key is rejected.

Portable restore recognizes only explicitly marked zero-value adjustments with matching item, direction, quantity, date, reason and zero movement value. It requires the recorded pre-adjustment quantity/value basis and checks the original zero-cost arithmetic. Where the adjustment is the only movement for its item on that date, the basis is reconciled against preceding dated movements. On dates containing marked decreases, day-end stock must not be negative or retain value at zero quantity.

The historical format does not retain a reliable ordering among same-day movements. These checks do not invent an order or claim signed provenance for editable backup data, and do not reprice unrelated legacy stock. Both legacy portable and complete ZIP backups retain the physical movement and its valuation basis. Older servers that do not recognize this new non-journal movement must be upgraded before restoring such a backup; no data is silently omitted.

## Verification

- Full backend suite: 244 tests passed; eight focused adjustment tests passed.
- Independent review reproduced and then verified rejection of matched quantity/movement tampering at quantities 1, 10 and 11. Snapshot validation, legitimate same-day write-off/restocking, paid valuation and access cases passed.
- Frontend: 153 tests, lint and production build passed, including the zero-value explanation rendering test.
- Five isolated HTTP workflow tests and the complete-backup HTTP roundtrip passed. The latter retained archived evidence through a 6,402,961-byte archive in 13 chunks of at most 512 KiB.
- Native API route scan: 232 routes matched. No native source or request schema changed; new native builds/device execution were not run for this local checkpoint.
- Deployment helpers: nine backup-target and 21 management mock tests, plus simulated backup/transactional restore safety checks passed. These do not execute a deployment. The encrypted infrastructure-backup CLI check was not run locally because `age` and `age-keygen` are unavailable.

All fixtures for this change are synthetic and isolated. No production data, schema migration or client payload change is involved. Hosted CI for this new checkpoint is pending publication; the preceding PR12 PostgreSQL suite passed, but is not claimed as execution of this patch.
