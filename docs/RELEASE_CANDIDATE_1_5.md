# Apex Books 1.5.0 candidate

This is a draft-branch candidate, not a published or deployed release. See [verification gates](RELEASE_VERIFICATION.md) for what has and has not been exercised on the exact source revision.

## Changes

- Stronger tenant/role checks, financial retry identity, period-lock enforcement, allocation and stock-cost validation, and portable-restore consistency.
- Faster compact company loading, fewer requests, stale-company response guards, explicit loading boundaries and richer read-only document journeys across clients.
- Nonposting sales orders, low-stock reorder review, repeat-party price history, payment-term suggestions, archive/reactivate masters, delivery addresses and informative credit limits.
- Explicit recurring draft generation: no automatic financial posting.
- Separate book labels without changing the legal company name or printed invoice identity; shared India business-date defaults and feature-capability negotiation.
- Retained purchase/expense receipts and consistent complete ZIP backups. Every retained receipt, including archived files, is included; legacy export routes refuse to silently omit evidence.
- Complete transfers use authenticated bounded chunks with hashes, cancellation, staging expiry, explicit preview/restore and recoverable canonical restore results.
- Existing encrypted portable-v1 backups remain compatible. Encryption and decryption remain client-local; passphrases do not go to the API. Large native transfers use file-backed processing, while web tools enforce conservative memory limits rather than omit data or drop encryption.
- Explicit percentage/fixed-rupee line discounts preserve existing amounts during editing and conversion. Linked returns require review of fixed discounts; they are never silently prorated. PDF layouts display the actual discount input.

## Added after the first candidate: cancellation, payment at entry, statements

- **Cancel a posted document** (`POST /records/{id}/cancel`, reason required): sales invoice, POS sale, purchase bill, payment in/out, expense, credit/debit note or bank transfer. The ledger entry is reversed with a linked reversal journal, tracked stock is released, payment/note allocations are freed, the document number is kept and the action is audited. Cancellation is refused with an explanation while payments, notes, settlements, bank matches or later stock sales depend on the document. Locked periods apply. It cannot be undone.
- **Received now / Paid now** (`POST /records/with-payment`): an invoice or bill and its first receipt/payout post in one transaction under one retry key; an invalid payment saves neither. Web, Windows and Android show it on the new-document form.
- **Profit & loss and balance sheet** (`GET /reports/statements`, `.pdf`, `.xlsx`): revenue, cost of sales, gross profit and margin, other income, operating expenses and net profit; classified assets, liabilities and equity including retained profit brought forward, with an explicit balance check. The previous list is kept as "Account balances".
- Reports and registers exclude cancelled documents; the cash book shows a cancelled document by number; the items report no longer gives services or untracked goods a stock quantity; a linked item's HSN/SAC is filled by the server when a line leaves it blank.
- New capability flags `document_cancellation`, `payment_at_entry` and `financial_statements` are advertised by `/api/capabilities`. Web, Windows and Android hide the new controls and report when the API does not advertise them.

## Compatibility and rollout

API and web package versions target 1.5.0. Android targets version 1.5.0 (code 12); Windows targets 1.5.0 (package 1.5.0.0). Version changes do not imply signing, distribution or production promotion.

No schema migration is required for cancellation, payment at entry or statements. **Rollback caution:** a cancelled document keeps its original and reversal journals but loses its posting link, so an older API build shows it as an unposted legacy record; restore from a verified backup rather than downgrading after cancelling documents.

Additive migrations include company labels, retained evidence and bounded transfer staging. Test and back up the intended deployment before applying migrations; these development changes do not apply them to live books. Existing company IDs and legal identities must be preserved deliberately.

Clients negotiate optional features with the API. An older API does not gain a capability just because a new client displays it. Old JSON/gzip backup imports remain supported within their documented limits; complete evidence backups use the v8 ZIP API. Older clients receive an explicit complete-backup requirement when receipts exist.

Operational requirements include an explicit strong JWT secret. OCR requires HTTPS outside loopback by default; an operator may explicitly configure `OCR_ALLOW_INSECURE_HTTP=1` for an approved existing HTTP provider, accepting that provider credentials and document bytes then lack transport encryption. There is no automatic downgrade or client-side key. VPS preflight validates the same configuration rules before cutover.

## Build identity

Supply the full verified source commit SHA explicitly as `APEX_BUILD_SHA` for the API/native build and `VITE_BUILD_SHA` for the web build. These values are public, non-secret metadata. CI records the actual checked-out revision after checkout (including fixed-source test runs), not an assumed event revision. API capabilities/health/readiness and client Settings/About expose version and source identity. Missing or malformed revisions display `unknown`; there is no server/runtime git command or invented source identity. A local dirty-tree validation artifact must not be described as an immutable release build merely because a test SHA was supplied.

## Not claimed

No zero-defect or comprehensive security certification; no automatic statutory filing, signed store release, production deployment, durable offline financial-posting queue, or new cashier/accountant permission model. Newest native runtime, release-build and responsive-browser evidence must meet the verification ledger before live promotion.
