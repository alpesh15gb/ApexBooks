# Cross-client release verification

This is a verification ledger, not a claim of zero defects or security certification. Draft-branch work is not a production deployment. Release-suite fixtures are synthetic and isolated. Rehearsals of supplied backups were performed separately in private, isolated databases; those backups and accounting records are not published.

## Complete application candidate

Local commit `3e6d06268e11b36e32a3c05284c1a364b7c52860` and published commit `87ee6f3a9276f6992fc18425323b21cb52592d79` have the identical source tree `b2f4ce9421b225cecfcff296e9313ae2afb4dc8a`. Running `PYTHON=/path/to/test/python bash scripts/check.sh` from an exact git archive passed:

- **184 backend tests**, including balances, stock cost, allocations, tenant/role checks, restore lineage, recurring drafts, master lifecycle, credit warnings, retained receipts, fixed discounts and retry semantics.
- **110 web tests**, lint and production compilation.
- Five core HTTP journeys and one complete-backup HTTP journey: a 6,402,966-byte archive transfers in 13 parts of at most 512 KiB; archived receipt hashes survive restore, source reports remain unchanged and commit replay creates one company.
- **231 native API route literals**, with no unmatched routes.
- Simulated transactional infrastructure-backup safety. Local `age` was unavailable; real encrypted infrastructure-backup checks are covered by the hosted synthetic job, not by that local result.

Additional native evidence on this candidate:

- Android: **48 unit tests, no failures/skips**, including live local HTTP receipt upload/archive, complete transfer/restore/replay, fixed-discount preservation and delayed optional-capability checks without blocking core requests. Debug and unsigned Release/R8 builds, lint, APK/AAB and instrumentation APK completed. Lint reported zero errors, with 16 Debug and 15 Release advisories.
- Windows: **133 portable checks** and semantic compilation passed, including live local HTTP transfers/discount preservation and independent optional capability loading.
- Established streaming encryption libraries preserve encrypted-v1 compatibility. Java/.NET cross-writer, escaped-base64, authentication-failure, truncation and cancellation fixtures passed; 320 MiB pipelines were exercised under 64 MiB managed-heap limits. These are host-process measurements, **not Android device memory evidence**. See [native backup verification](../native/BACKUP_VERIFICATION.md).
- Both supported supplied-book rehearsals separately preserved five report values through legacy and v8 ZIP restore, including commit replay. Those source archives contained no attachments; evidence-byte coverage comes from synthetic fixtures. Two other supplied backups remain blocked on unsupported historical adjustments, not silently imported or merged.

## Hosted and interactive gates

Status recorded while the exact-source Android recovery run is pending. A local build or an older green job does not substitute for a newest-source runtime result.

| Surface | Established evidence | Remaining or corrective gate |
| --- | --- | --- |
| API/web | Hosted synthetic API/web and dedicated PostgreSQL concurrency jobs passed on published `87ee6f3`; quota/concurrent restore checks run against PostgreSQL, not inferred from SQLite | Production-like isolated deployment/migration/recovery drill and actual target configuration verification |
| Web browser | Earlier real responsive billing, navigation, company selection and book-label journeys passed; newest receipt/complete-backup flows have unit and HTTP coverage | Newest receipt upload/encrypted-backup responsive browser interaction remains pending the original browser tool approval; no bypass or equivalent reroute performed |
| Windows | Real hosted UI created an invoice, recorded a partial receipt, verified remaining balance/one allocation and dirty-dialog decisions; unsigned Release job passed | New receipt picker step timed out; owned-dialog selector correction compiles but needs hosted rerun. A separate locked dependency restore failed after a conflicting RID restore; isolated per-RID lock correction passes both local restore orders and needs hosted rerun |
| Android | Hosted unit/lint/build and unsigned Release jobs passed on `87ee6f3`; local real HTTP checks passed. The corrected isolated emulator reached instrumentation: **three of four tests passed** | The real UI journey failed locating the low-stock item; artifact-based scrolling/visibility diagnosis and exact-source rerun are pending. Temporary KVM ACL restoration and comparison succeeded. Earlier pretest attempts exposed prerequisite ordering, AVD-home and SDK/runtime dependency failures; none are treated as application acceptance passes |

Actual PostgreSQL checks are required for simultaneous numbering, stock consumption, allocation consumption, retry keys, receipt quotas and complete restores. Physical-device printing/sharing, signed clean installation/update and real low-memory Android behavior have not been established by these suites.

## Separate deployment-readiness corrections

Local `730efcbde0a4c770552feee618026182b474136f` adds fail-closed release identity and backup-target checks; local `5093e3346acd9352e9277ccd5a6db33f255cf428` adds the narrow Windows CI corrections above. These are separate from the pinned application candidate. Readiness changes and the subsequent timer/build-identity corrections passed the complete isolated suite plus nine mocked backup-target tests, twenty-one mocked VPS tests and simulated dump/restore handling. The final precommit isolated tree was `101c3680fd415e9ef584ef11178b0821a3f5fd1d`; documentation may subsequently record new runtime outcomes without changing those tested sources. No actual Docker, SSH, database, credential or production operation was executed by those readiness tests. Hosted verification of these follow-up commits remains a gate. The next combined candidate also fixes the Android dashboard's remaining host-calendar default and adds genuine scrolling to the device UI journey without removing assertions. Local verification passed 49 Android tests plus Debug/unsigned Release/R8/lint/APK/AAB builds, 133 Windows portable checks, and 111 web tests plus lint/build. A rendered web-dashboard regression checks the actual summary, financial and GST query dates across India midnight and financial-year boundaries. Newest hosted/device reruns remain pending.

The generic backup helpers support only the reviewed root local-Compose database and require explicit scope. They are not a hosted-provider recovery procedure. A company ZIP is not a full-database recovery point. See [backup boundaries](../deploy/SECURE_BACKUP.md) and [release preflight](../deploy/vps/README.md).

## Deployment mapping and recovery remain unverified

Repository documentation describes a Vercel preview and separate production web/API origins. The observed Vercel preview deployment is older than this candidate, has no source revision in its inspected metadata and has no production custom domains attached to that inspected project. Database environment entries were observed without reading their values: **database sharing versus isolation is unknown**, not proven either way. No current deployed source, database identity or production health is inferred from these facts.

Before promotion, identify the intended web/API front doors, actual database and every writer sharing it; verify exact build revisions and migration state. The 1.5.0 native Release origin is `https://api.apexbooks.in`, so a preview-only rollout does not automatically update native behavior. No live configuration or deployment has been changed by this work.

Establish a verified full-database recovery point/PITR and isolated restore rehearsal before migration. Proxy/container rollback does not undo schema or data. Downgrading the new label, receipt or transfer migrations can discard retained information; do not use destructive downgrade as a routine rollback. Plan write freeze or post-cutover write reconciliation, recovery time, retention and capacity monitoring. Provider credentials, production migrations and recovery operations remain separate operator actions.

## Explicit product and security boundaries

- No automatic invoice posting, restore replacement, scheduled recurring posting, receipt rendering or external statutory filing is introduced. Recurring occurrences and reorder suggestions require review; prices/terms require explicit application; credit warnings do not silently block established books.
- Archived receipts retain evidence and quota. Legacy exports refuse to omit receipts and direct the user to a complete backup.
- Web buffered transfers have conservative limits and an explicit native alternative; no partial omission or encryption downgrade. Host memory measurements do not prove mobile-browser safety.
- Financial retry holders protect a live session/navigation and tested native activity recreation, not full process death. There is no durable offline posting queue or crash-proof exactly-once claim.
- Existing owner/editor/viewer roles remain. Finer cashier/accountant permissions and inline create-and-use masters are not claimed as implemented.
- Dependency advisory scans are point-in-time known-finding checks, not security certification; rerun after dependency changes. An independent broader security review did not complete. Existing negative tenant/role, validation, import/restore and session tests remain evidence, not a comprehensive penetration assessment.
- Android 1.5.0 Release APK/AAB and Windows portable artifacts are unsigned verification outputs. Signing, distribution, clean install/update, signing-key continuity and store acceptance have not occurred. Historical checked-in installers are not the new tested release.

## Before live promotion

Close the newest-source UI/CI gates, verify source identity across API/web/native artifacts, perform isolated migration and recovery drills, verify explicit JWT secret and HTTPS OCR transport, and preserve source-book identities. Merging a draft branch does not complete these operational gates. Do not describe this candidate as fully deployed, fully secure, zero-defect or universally feature-complete.
