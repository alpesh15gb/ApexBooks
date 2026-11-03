# Inline item and service creation during a sales invoice

## Bounded scope

The web new-sales-invoice editor can create an item/service and use the returned catalogue identity without leaving the draft. This follows the inline-party workflow. Existing documents, conversions, linked returns, purchases and native clients retain their existing master-register workflows.

A successfully created catalogue entry remains available even if the invoice is later discarded. Cancelling the creation form before submission creates nothing.

This uses the existing company-scoped idempotent master-create API. It adds no API route, migration, opening stock, journal or automatic invoice posting. The invoice still requires separate review and save. A new stock-tracked item has no inventory simply because a purchase rate was entered: stock must come from a real purchase or reviewed opening before it can be sold.

## Safety and acceptance

- Preserve existing invoice rows, quantities, rates, fixed/percentage discounts, party, date, manual delivery address and notes.
- Use only the newly returned master identity and its reviewed catalogue defaults for the new line. Do not overwrite an existing edited line. Only a sole, exactly untouched placeholder is reused; edited blank rows are retained. Successful creation focuses the new quantity for review, including the 100th line.
- Retain exact request body, explicit business date and idempotency key across uncertain-response retries, including midnight. Block dismiss/navigation and invoice save while the response is uncertain.
- Show duplicate/validation errors without silently selecting another master. Reject late company/session responses.
- Preserve item tax treatment, HSN/SAC and units; services do not require stock. Keep the 100-line document limit.
- Cancellation returns to the same mounted invoice and restores keyboard focus. No nested HTML forms or hidden editable invoice controls while the master form is active.

## Verification

`backend/test_inline_item.py` uses isolated synthetic HTTP calls to prove master-create replay is non-posting, duplicate names are rejected, a tracked item cannot be sold without stock, a non-GST service preserves its fixed discount, and a foreign-company item cannot be used on an invoice.

`frontend/tests/inlineItem.test.mjs` adds 15 real React/jsdom interaction tests for cancellation/focus, retained quantities and fixed/percentage discounts, goods/services and tax defaults, numeric/string zero rates, the 100-line limit, pristine-placeholder handling, duplicate/validation errors, exact-body/key/date retry across midnight, stale company/session responses and unsupported-context restrictions. The nine inline-party tests remain green.

Local aggregate verification on 2026-11-03 passed 200 backend tests, 142 frontend tests, lint and production build, five synthetic HTTP workflows, one complete-backup HTTP round trip, 231 native API route matches, nine backup-target and 21 deployment-preflight mocks, and simulated backup/restore checks. Real-age infrastructure-backup checks were not run locally because `age`/`age-keygen` are unavailable. The existing bundle-size warning remains.

No new real-browser visual/keyboard acceptance or hosted CI run is claimed for this checkpoint. Native inline creation remains outside this web-only scope. No production data or permissions are needed. Real-browser access and upload approval are separate; neither is bypassed by these tests.

Retry state remains in memory. Browser process death is not covered by this flow and no exactly-once or offline-posting guarantee is made.
