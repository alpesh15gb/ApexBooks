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

The corrected combined source is local `a7e8f5e4814083249a3cee442c4dfe88ca5edbef` / published `e4a7e9f23b5671d4b5a1340a33e33fe2ee8a4b83`, with identical tree `e58a8ded4d24d9d7bc67cd01ae1b857909301ab0`. Published `f3a296fe2961dbc38d3a266913553c3f54611423` adds only the narrowly scoped device-run workflow and pins Android acceptance to that application source.

On this corrected candidate, **all four main CI jobs**, **both unsigned Release jobs**, and the **real Windows UI journey passed**. This includes the new deployment-readiness mocks, real `age` infrastructure-backup fixtures, PostgreSQL concurrency and per-RID locked Windows restores. The subsequent narrow Android accessibility and test-fixture corrections have now also passed actual emulator acceptance; the exact source and coverage are recorded below.

| Surface | Established evidence | Remaining or corrective gate |
| --- | --- | --- |
| API/web | Hosted synthetic API/web and dedicated PostgreSQL concurrency jobs passed on corrected published `f3a296f`; quota/concurrent restore checks run against PostgreSQL, not inferred from SQLite | Production-like isolated deployment/migration/recovery drill and actual target configuration verification |
| Web browser | Earlier real responsive billing, navigation, company selection and book-label journeys passed; newest receipt/complete-backup flows have unit and HTTP coverage | Newest receipt upload/encrypted-backup responsive browser interaction remains pending the original browser tool approval; no bypass or equivalent reroute performed |
| Windows | Corrected hosted UI created an invoice, recorded a partial receipt, verified remaining balance/one allocation and dirty-dialog decisions, then uploaded a receipt through the real picker, checked its size/hash/lineage, archived retained bytes and opened complete backup. Per-RID locked restore/build and unsigned Release passed | Physical printing/sharing and signed clean installation/update remain unverified; these CI passes are not distribution acceptance |
| Android | **Four instrumented tests passed, zero failures/errors/skips**, on exact source `45cd1a628d40f6a1348aacede04af9a6ecb2575c` (local `ecdd247`, tree `0d409104501a0d934135d609ceffafd58a110488`). Real UI passed invoice/collection, company selection, reorder/price/terms, dirty discard, canonical new-invoice checks, actual receipt picker/upload/archive with byte hash/size assertions, and complete-backup entry with encryption enabled | The earlier four-test pass covered backup entry only. A later run saved the encrypted backup, but the full Android decrypt/restore UI remains pending; see the latest evidence below. Physical-device printing/sharing, signed update and low-memory behavior remain separate gates |

Android proof: [run 41556754728](https://github.com/alpesh15gb/ApexBooks/actions/runs/41556754728), job `125657424839`, artifact `13194754040`; workflow head `38e49c7752456bd4f7856905d22a5b26b7d02df8` checked out the exact application source above. The final cleanup restored the saved KVM ACL and compared the before/after ACL successfully. Earlier prerequisite or UI failures are not counted as passes. The corrected shared choice/date controls have accessible labels and roles; the dashboard uses the India business day.

The normal Android device job now intentionally **skips** on ordinary pull requests/pushes. A separately authorized `workflow_dispatch` with its default-false permission input enabled is required to run it. There is no permanent run-number/source gate or standing automatic device permission change. Main CI continues Android unit/lint/build checks. A skipped later job does not erase or rerun the exact-source runtime proof above and must not be reported as a new device-test pass.

Actual PostgreSQL checks are required for simultaneous numbering, stock consumption, allocation consumption, retry keys, receipt quotas and complete restores. Physical-device printing/sharing, signed clean installation/update and real low-memory Android behavior have not been established by these suites.

## Separate deployment-readiness corrections

Local `730efcbde0a4c770552feee618026182b474136f` adds fail-closed release identity and backup-target checks; local `5093e3346acd9352e9277ccd5a6db33f255cf428` adds the narrow Windows CI corrections above. These are separate from the pinned application candidate. Readiness changes and the subsequent timer/build-identity corrections passed the complete isolated suite plus nine mocked backup-target tests, twenty-one mocked VPS tests and simulated dump/restore handling. The final precommit isolated tree was `101c3680fd415e9ef584ef11178b0821a3f5fd1d`; documentation may subsequently record new runtime outcomes without changing those tested sources. No actual Docker, SSH, database, credential or production operation was executed by those readiness tests. Hosted verification of these readiness and Windows corrections subsequently passed on `f3a296f`. The next combined candidate also fixes the Android dashboard's remaining host-calendar default and adds genuine scrolling to the device UI journey without removing assertions. Local verification passed 49 Android tests plus Debug/unsigned Release/R8/lint/APK/AAB builds, 133 Windows portable checks, and 111 web tests plus lint/build. A rendered web-dashboard regression checks the actual summary, financial and GST query dates across India midnight and financial-year boundaries. Hosted main and unsigned Release reruns passed; the later exact-source Android runtime proof above closes the previously failing instrumented journey.

The generic backup helpers support only the reviewed root local-Compose database and require explicit scope. They are not a hosted-provider recovery procedure. A company ZIP is not a full-database recovery point. See [backup boundaries](../deploy/SECURE_BACKUP.md) and [release preflight](../deploy/vps/README.md).

## Latest full-build and encrypted backup evidence

Published application source `12e63d1b299f043532b7838ab598e6db92f754d9` matches local `d9e526ff01ab52c86f7ca8e9396cb742f9dc0e3f`. Gate head `1d46468572c57c3124de75c00b86ca38200f006e` passed all four main CI jobs (run `41576732037`) and both unsigned Release jobs (run `41576731922`). This includes the full Android rebuild and production-method lifecycle regression that could not run after local SDK loss.

The **Windows full encrypted backup UI roundtrip passed**, run `41576732072`, job `125721857127`: actual encrypted Save picker, Open picker, password authentication, preview, explicit restore into one new company, canonical reports and retained archived receipt bytes/hash, with the original company unchanged. The rapid-typing invariant and earlier financial/receipt assertions remained required.

Android run `41576731916` successfully saved the encrypted backup through the actual picker. The next picker navigation selected an ambiguous Downloads toolbar label rather than the drawer root. A test-only correction scopes that row to DocumentsUI's `roots_list` and requires the drawer and picker to dismiss before proceeding. The captured hierarchy distinguishes two old matches from one correct scoped match. That selector correction compiled and passed main/Release CI. The following device attempt completed Save, Open and encrypted-file detection, then a generic scroll gesture hit the visible Android keyboard instead of the form. The next test-only correction dismisses only a positively identified keyboard before scrolling and asserts the restored-company name remains exact. The complete Android authenticate/preview/restore runtime still requires a successful rerun; no app behavior or financial assertion was changed. Temporary KVM ACL restore and comparison succeeded. Main CI `41578065687` and unsigned Release `41578065578` passed all jobs, and Windows full encrypted recovery passed again in `41578065585`.

## Restore navigation cancellation correction

A deterministic local coroutine regression reproduced a real Android load-lifetime defect: opening a restored company from the dialog-owned scope cleared that dialog before the pending record/bank loads completed, leaving the new company selected with `recordsReady=false`. The correction dispatches only this navigation through the existing ViewModel-owned task and retains the company/session generation guards and loaded-state success check. `native/tests/AndroidLifecycle/check.py` compiles the actual production `chooseCompany` and `task` bodies with controlled suspension barriers and verifies both the old cancellation case and corrected lifetime. It uses existing Gradle Kotlin/coroutines libraries, no network or Android runtime. The full Android rebuild and this lifecycle regression subsequently passed in main CI run `41576732037`; the actual restored-register UI assertion remains required. The older entry-only device pass is not evidence for this changed app line.

## Known-baseline upgrade rehearsal

The pinned original repository `1e8d981149e8a4dce597ec49933b33887bcf00d6` was upgraded in an isolated synthetic SQLite rehearsal: readiness 503→200, all original rows/columns across 33 tables preserved, six reports equal, repeated migration unchanged, and the original application reopened its pre-upgrade physical backup. A receipt added after upgrade and complete ZIP restore preserved bytes, financials and exact commit replay. No original 1.3 receipt storage is implied. The actual production schema, PostgreSQL migration behavior at production scale and provider recovery remain unverified. See [the detailed 1.3→1.5 checklist](UPGRADE_1_3_TO_1_5.md) and `tests/upgrade/rehearse_legacy.py`.

The native encrypted save-picker→restore-picker→new-company UI tests are a separate new extension; they compile locally but are not covered by the earlier entry-only device pass. They assert canonical reports and retained evidence bytes while leaving the original company unchanged. The first extended runtime attempt reached encrypted export preparation, but Android clicked an action before it was enabled and Windows encountered shell UIA reentrancy when invoking Save. Narrow test corrections now wait for verified/inspected/enabled UI states and activate the focused real Windows Save button once through the keyboard; compiled corrections still require the full runtime roundtrip. No export/restore API substitute or financial assertion removal was introduced. The Windows item-typing regression retains a mandatory rapid whole-string input check, exact text and stable focused control identity; it does not replace fast typing with a paced-only test.

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
