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

## Compatibility and rollout

API and web package versions target 1.5.0. Android targets version 1.5.0 (code 10); Windows targets 1.5.0 (package 1.5.0.0). Version changes do not imply signing, distribution or production promotion.

Additive migrations include company labels, retained evidence and bounded transfer staging. Test and back up the intended deployment before applying migrations; these development changes do not apply them to live books. Existing company IDs and legal identities must be preserved deliberately.

Clients negotiate optional features with the API. An older API does not gain a capability just because a new client displays it. Old JSON/gzip backup imports remain supported within their documented limits; complete evidence backups use the v8 ZIP API. Older clients receive an explicit complete-backup requirement when receipts exist.

Operational requirements include an explicit strong JWT secret. OCR requires HTTPS outside loopback by default; an operator may explicitly configure `OCR_ALLOW_INSECURE_HTTP=1` for an approved existing HTTP provider, accepting that provider credentials and document bytes then lack transport encryption. There is no automatic downgrade or client-side key. VPS preflight validates the same configuration rules before cutover.

## Build identity

Supply the full verified source commit SHA explicitly as `APEX_BUILD_SHA` for the API/native build and `VITE_BUILD_SHA` for the web build. These values are public, non-secret metadata. CI records the actual checked-out revision after checkout (including fixed-source test runs), not an assumed event revision. API capabilities/health/readiness and client Settings/About expose version and source identity. Missing or malformed revisions display `unknown`; there is no server/runtime git command or invented source identity. A local dirty-tree validation artifact must not be described as an immutable release build merely because a test SHA was supplied.

## Not claimed

No zero-defect or comprehensive security certification; no automatic statutory filing, signed store release, production deployment, durable offline financial-posting queue, or new cashier/accountant permission model. Newest native runtime, release-build and responsive-browser evidence must meet the verification ledger before live promotion.
