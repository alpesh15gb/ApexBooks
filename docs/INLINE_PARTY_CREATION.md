# Inline party creation while drafting an invoice

## Scope

This separate follow-up adds one web workflow: create and use a party from a new sales invoice without leaving the invoice editor. It does not add inline item creation or native-client inline forms. Existing master registers remain available on every client.

The flow uses the existing company-scoped `POST /api/companies/{company_id}/records` master endpoint. Creating a party does not post an invoice, journal, receipt, or opening balance. The invoice is posted only after its separate review and save.

## Acceptance requirements

- Keep invoice lines, date, notes, explicit due date and manually entered delivery address when entering, cancelling or completing party creation.
- Populate the selected party's identity and contact defaults only after a successful response; do not silently apply payment terms or submit the invoice.
- Keep the invoice editor mounted. Make the inline form keyboard accessible, give fields unambiguous labels and restore focus when returning to the invoice.
- Disable invoice submission while party creation is open or its response is uncertain. Freeze the submitted party request and idempotency key for an uncertain-response retry; never retry automatically with changed details.
- Reject duplicate names visibly. Do not silently select a different existing party after a conflict.
- A late response must not populate another company's or another signed-in user's editor.
- Viewer and nonmember requests remain denied server-side, including replay attempts. Party IDs from another company must not be accepted on an invoice.

## Verification and limits

`backend/test_inline_party.py` uses isolated synthetic HTTP calls to verify non-posting master creation and exact-key replay, duplicate rejection, preserved explicit invoice values, tenant-scoped idempotency, viewer/nonmember denial and cross-company identity rejection.

`frontend/tests/inlineParty.test.mjs` exercises the real React editor and forms in jsdom: cancellation, focus return, retained invoice values, duplicate rejection, same-tick dismissal protection, exact-body/key/date retry across midnight, uncertain invoice protection, stale session/company responses, viewer restrictions and existing-document exclusion. The explicit master creation date prevents a changed server-default date from invalidating a recovery request after midnight.

Local aggregate verification on 2026-11-03 passed:

- 198 backend tests and 127 frontend tests; frontend lint and production build.
- Five synthetic HTTP workflow tests and one complete-backup HTTP round trip (13 bounded chunks with archived evidence hashes preserved).
- 231 native API routes matched, nine backup-target mocks, 21 deployment-preflight mocks and simulated backup/restore checks.

This batch changes web UI and adds API regression tests, not native UI. It has not received a new real-browser visual/keyboard acceptance run or hosted CI run. Existing pending browser upload approval was not bypassed. Real-age encrypted infrastructure-backup tests were not run locally because `age`/`age-keygen` are unavailable. Existing production bundle-size warning remains. No production records, migrations or configuration are needed for this flow. No new file-upload path is involved.

Retry state is held in the live editor only. This feature does not provide durable recovery after browser process death and must not be described as crash-proof or exactly-once offline posting.
