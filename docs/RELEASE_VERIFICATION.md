# Cross-client release verification

This is a verification ledger, not a claim of zero defects or security certification. Draft-branch work is not a production deployment. All test records are synthetic and isolated.

## Current completed source checkpoint

`dac5fae` contains the API/web retained-receipt and complete-backup implementation. Running `PYTHON=/path/to/test/python bash scripts/check.sh` from an exact git archive passed:

- 179 backend regression tests, including accounting balances, stock cost, allocation limits, tenant/role checks, restore lineage, recurring drafts, master lifecycle and credit-warning semantics.
- 99 web tests, lint and production compilation.
- Five existing HTTP journeys and one complete-backup HTTP journey: a >6 MiB archive is transferred as 13 parts of at most 512 KiB, archived receipt hashes survive restore, source reports do not change, and commit replay creates only one company.
- 207 native API route literals matched the API contract at this checkpoint.
- Simulated transactional backup safety. The local machine lacks `age`; encrypted infrastructure-backup checks are a separate hosted CI gate, not implied by the local result.

Actual PostgreSQL concurrency checks run in the dedicated CI service. SQLite success alone is insufficient evidence for simultaneous document numbers, stock consumption, allocations, retry keys, receipt quotas or complete restores.

## Client and platform gates

| Surface | Evidence already established | Remaining gate for the newest complete candidate |
| --- | --- | --- |
| API | Full isolated regression and HTTP journeys; prior PostgreSQL integrity checks passed | Exact-candidate PostgreSQL receipt quota/deduplication/concurrent restore checks |
| Web | Unit/jsdom journeys, actual earlier responsive billing and company-label journeys | Actual newest receipt and encrypted complete-backup responsive browser journey; tool approval may be pending |
| Windows | Hosted real UI created an invoice, recorded a partial receipt, checked remaining balance and one allocation; dirty-dialog keep/discard tested | Build and UI verification of newly integrated receipts/streamed complete backups; unsigned Release artifact check |
| Android | Real Kotlin/unit/lint/debug/instrumentation builds passed before newest receipt integration | Newest native integration build; approved isolated emulator run; unsigned R8 Release APK/AAB check |

Native incremental encrypted-backup work must preserve the existing portable v1 format, authenticate before uploading or exposing plaintext, and verify cross-writer fixtures, wrong password, truncation, cancellation and bounded memory. Host-JVM/.NET memory measurements are not Android device measurements.

## Explicit boundaries

- New receipt storage and transfer staging use additive migrations; these source changes do not apply production migrations.
- No automatic invoice posting, restore replacement, scheduled recurring posting, attachment rendering or external statutory filing is introduced.
- Recurring occurrences are saved drafts for review. Reorder and price/term suggestions require explicit application. Credit warnings do not silently block established books.
- Receipt archive retains evidence and quota. Legacy exports refuse to omit retained receipts and direct the user to a complete backup.
- Web buffered transfers have conservative size limits with an explicit native alternative, never partial omission or silent removal of encryption. Whole-buffer WebCrypto is not suitable for unlimited mobile archives.
- In-memory financial retry holders protect a live session/navigation (and native activity recreation where tested), not full process death. Do not describe them as a durable offline posting queue or crash-proof exactly-once delivery.
- Existing owner/editor/viewer roles remain. A cashier/accountant permission model is not claimed without exhaustive route and data-visibility enforcement.
- Runtime dependency advisory scans report known findings at a point in time; they do not certify security. Re-run after each dependency change.

## Before live promotion

Verify the exact release SHA across CI, API version and native artifacts; exercise the native/UI gates above; review migration/rollback and backup retention in an isolated deployment; verify explicit JWT secret and HTTPS OCR configuration; preserve real-data backup and source-book identity. Production migration, signing/distribution and promotion remain separate operator actions. Do not infer that merging a draft branch has already completed these operational gates.
