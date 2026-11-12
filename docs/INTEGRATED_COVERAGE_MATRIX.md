# Integrated candidate coverage and release gates

This is a review candidate, not a production-ready declaration or a claim of comprehensive Indian accounting/GST compliance. The user owns deployment. No production data, credentials or systems were accessed for this checkpoint.

## Current reconciliation (2026-11-12 follow-up)

The revision inventory and aggregate results below describe the historical 9159
checkpoint unless explicitly dated as a follow-up. They are not final-stack CI
results. The local branch now includes these corrections:

| Finding family | Local correction | Independent review reported by parent | Remaining gap |
| --- | --- | --- | --- |
| Settled notes and dependent payments | `9db279c` | 40 tests plus customer/supplier repeated restores passed | Actual-book audit and operator recovery rehearsal |
| Party PDF and native PDF/share scope | `41ef08e`, `5e65e6b` | PDF visual checks and compiled request/share tests passed | Tagged PDF/accessibility and native rendering/printing |
| XLSX fidelity, casefold party/item identities | `ae7e9a7`, `e46744f`, `28ded2e` | Export and identity tests passed | Lookup still scans masters; broader historical inventory incomplete |
| Native denied-access and pending reads; web access recovery | `e46744f` through `bb5a5e5` | Review exposed follow-on gaps, addressed in later commits | Full native app/device acceptance and final browser revocation matrix |
| Retained stock drafts after viewer recovery | `78ddeb1` | Seven rendered recovery and eight handler-body authorization cases passed | Final browser acceptance |
| Member-removal confirmation and role-aware shortcuts | `7eda259` | Six existing tests plus in-flight Escape, late-success and owner-row probes passed | Confirmation focus/keyboard/browser acceptance |
| Audit labels/scoped refresh and backup acknowledgement | `bcc8d89` | Parent reported 18 tests plus stale-error and checkbox behavior probes passed | Actual narrow-screen and zoom visual acceptance |
| Native successful responses and logout/401 ownership | `d38c806`, `35d4e0e` | Parent verified transport regressions, including same-token replacement | Full native runtime and external side-effect acceptance |
| Android final Save picker ownership | Current local follow-up | 14 compiled actual-method/wiring scenarios; 46 transport scenarios rerun | Real picker/provider behavior; Windows picker boundary remains to review |

Parent's real-browser samples were on an isolated **9159** instance, not this final
branch: CSV duplicate handling, bank reconciliation and duplicate import, complete
backup/restore dashboard equality, retained attachment byte identity/reactivation,
viewer/editor roles, high-zoom navigation, invoice trails/totals, return defaults,
period-lock rejection and stock overview passed sampled scenarios. Later observed
revocation deficiencies led to the access corrections above. These observations
are valuable partial evidence; they must not be presented as final-commit or
exhaustive feature acceptance.

The verified Gradle 8.14.3 compiler passed six extracted native-method harnesses.
An offline full Android build failed before compilation because the Android
Gradle plugin was not cached. Android SDK and Windows build tools are unavailable
locally. No final-commit native CI or device run has completed. See
`WEB_ACCESS_ANDROID_REPORT_RECOVERY.md` for exact commands and limitations.

Remaining clear gates: final-stack CI, complete browser/keyboard acceptance,
Windows/Android builds and real device/file/print/share flows, remaining lost-fix
inventory, and the operator-owned production recovery/migration/writer-pause
rehearsal. No new production actions or remote publication were performed.

## Revision and publication inventory

- Product tree checkpoint: `f29787f79ceca48a41c41063500bfa9ae45fa65f`, plus the standard-check wiring and this matrix in the candidate commit.
- Remote main checked read-only on 2026-11-12: `ee18418b542125092a0fe76eb8aa84055c68e351`. It is an ancestor of the local candidate; no concurrent main commits were overwritten.
- Remote draft PR59 checked read-only: `fc415d654e0f1a4afd2c335a2b1202586ec1c695`. Prior CI covered that checkpoint, not the subsequent local changes. Its recorded local counterpart is `d66c544`.
- The current local branch integrates the recovered PR56 base and reconstructed return, PDF, restore, session, import, payment/POS and later visual-review fixes. Original lost commits are not claimed recovered or comprehensively recreated. The chronological detail documents contain superseded open items; this matrix is the current summary.
- Later work remains local. No upload was attempted in this checkpoint. Earlier upload approvals/denials were scoped; this candidate is not implicitly cleared for publication by earlier PR59 CI or a previously approved smaller stack. Report any new automatic-review block verbatim before retrying under materially new authorization.

## Coverage matrix

“Automated” means executed synthetic checks unless explicitly marked pending. Source inspection, server rendering, JSDOM and portable helper compilation do not establish browser/device acceptance. Native shared behavior is not assumed from web parity.

| Feature / risk | API and accounting evidence | Web evidence | Windows / Android evidence | Remaining acceptance or limitation |
|---|---|---|---|---|
| Sign-in, tenant and roles | Access/owner/editor/viewer and company isolation tests | Accepted-session ownership, logout races, stale responses/streams and inert restoration regressions | Compiled client/helper checks exist | Final multi-user real-browser/native expiry and revocation flows; do not infer every lost security fix was reconstructed |
| Invoice, bill, expense, POS | Posting, GST components, caps, amendment and tender tests | Editor, preview, retry and validation regressions; server totals bridge | Existing client contracts/helpers; source changes reviewed | Exact-candidate full builds, device invoice entry and POS acceptance |
| Payment and linked payment retry | Canonical party identity, complete child terms, duplicate/lost-response tests | Frozen payload and scoped operation regressions | Retry helpers compiled; Android Save & new intent tests | Native UI lost-response/reset timing, offline/process-death coverage remains distinct |
| Credit/debit notes and stock returns | Source-line identity, ITC treatment, cumulative rounding, capacity, chronology and cancellation tests | Remaining quantity defaults, explicit source, note trail/actions | Android actual source-method seam; Windows production source gate/quantity helpers | Full source-selection UI confirmation, fixed-discount review and ambiguous-history workflows; some unsafe cases intentionally fail closed |
| Inventory and negative stock | Valuation/replenishment, adjustments, return and ledger reconciliation tests | API-to-production-React opening/increase/decrease test; stock overview | Quantity helpers; other flows source-level/earlier CI | Current device stock workflows; historical books not repaired |
| Reports and applied filters | Date bounds, balances, ageing, cash book, Item activity tests | Company/date scope, GST-to-ordinary period, stale-result/export tests | Cash export snapshot changes have helper/source evidence | Final browser/native export and printing; older all-time/custom choices need operator review |
| Cash/bank/reconciliation | Journal chronology, legacy ordering, cash balance tests | Duplicate/stale operation tests, negative closing cash explanation | Earlier source/helper changes | End-date closing balance is distinct from same-day intermediate order; bank review device acceptance |
| Party ledger | Opening/closing and export reconciliation | FY default, scoped reads, compact balance components, readable dates | Existing statement workflows | Real-browser hierarchy/reflow; native visual parity and OS print |
| Manual journals / Day book | Noncash/zero-net inclusion, control-account protection, reversal/source tests | Readable voucher/source links; cancelled history through repeat restore | Earlier native guards | Journal source UX currently web; malformed/legacy unverified sources intentionally have no inferred link |
| Quotations / orders / conversion | Nine-line GST/discount/rounding and conversion regressions | Eighteen PDF variants previously checked; cancelled conversion trail and restored lineage | Earlier compiled/client work | Final integrated visual nine-line entry, conversion and PDF/system-picker/device printing |
| GST entry / working papers | Shared checksum/state checks; JSON/XLSX/PDF warnings; unchanged provisional credit | Accessible mismatch feedback, preserved warnings, state-name/code selector | Native builds/entry consistency need exact-candidate checks | No registration verification, eligibility determination or filing; direct historical transaction snapshots and imported legacy data may still require correction |
| Statutory scope / payroll / withholding | Existing boundary checks only | Working papers labelled provisional/unfiled | No broader statutory certification | Entity/transaction-specific applicability review; unsupported statutory workflows cannot be claimed implemented |
| Imports / images | Atomic validation, metadata/CSV/image tests, APNG rejection | Preview/file/company and retry regressions | C# CSV suite and Kotlin CSV tests compiled previously | Full native picker/preview/commit and bad-encoding/device acceptance |
| Backup / restore | References, duplicate IDs, settlement capacity, balance/valuation, cancellation, repeat restore and atomic rejection | Transfer/hash/session ownership tests | Portable transfer/client tests | Actual production recovery rehearsal, attachment/object completeness, keys and restore access; no automatic historical repair |
| Historical integrity audit | Read-only synthetic finding/reconciliation tests | No production audit executed | Not a device task | Operator runs read-only audit on an authorized snapshot, assesses discrepancies and approves any corrections separately |
| Recurring drafts / reorder | Configuration excluded from Day book; draft generation | Draft/source preservation and PO-created link | Native parity not freshly accepted | Incoming quantity from unfulfilled POs is not inferred; duplicate ordering review remains an operator flow |
| Accessibility / responsive layout | Not an API claim | Rendered focus/inert/validation tests; drawer/filter CSS and test scenarios | No screen-reader/device certification | Actual keyboard-only nine-line entry, focus return, announcements, 320px / 400% short viewport and screen readers on final commit |
| Releases / upgrades | Synthetic safety tests and owned PostgreSQL verification | Bundle budgets and exact build identity mechanisms | Exact-candidate CI/device jobs pending | All production gates below; no deployment performed |

## Final production gates (operator-owned)

1. Independently review this exact candidate, resolve any new findings and obtain authorized publication if needed. Run all required CI on the exact immutable SHA; earlier PR results do not transfer automatically.
2. Build API/web/Windows/Android from that SHA. Match manifests, source/image hashes, served API/web revision and native build identity. Keep unsigned test artifacts private; do not distribute them as a release.
3. Finish the final-commit browser/device acceptance matrix, including roles/company switches, failed requests, duplicate submits, returns, exports, system file pickers and printing. Record observed outcomes, not just unexecuted test scripts.
4. Identify all writers to the actual database: every API deployment, worker, integration and native/web client path. Plan and verify a writer pause; stopping one Compose project is not sufficient.
5. Verify a fresh full-database recovery point plus attachments/object storage and required encryption keys; restore it into an isolated environment. Verify balances, stock, relationships and files there. A JSON company backup or retained container alone is not proof of full recovery.
6. Rehearse forward migrations against the actual schema/data clone, identify compatibility limits and retain recovery/forward-fix instructions. Generic proxy/container rollback is not database rollback; never restart old code blindly against a changed schema.
7. With all gates satisfied, the user/operator controls activation and smoke checks. Keep writers paused on failed migration/readiness; recover using the verified plan. Reconcile reports and test clients before resuming writers.

## Known nonblocking polish and unclosed inventory

- Backup unencrypted acknowledgement alignment is corrected locally; actual browser zoom/narrow-width acceptance remains open.
- State selection is a native name/code select with keyboard type-ahead, not a custom searchable combobox; existing unsupported saved codes remain visible and unchanged.
- Full native visual parity for the new totals, stock, journal and compact-ledger presentation is not claimed.
- Reconstructed fixes do not certify every earlier lost enhancement (including all historical report/export, numeric, authorization-concurrency and native session/cache refinements). Existing tests cover important cases; a complete old-to-new inventory is still a release-review task.
- No defensible delivery date is asserted while final CI, native acceptance and production recovery evidence remain open.

## Executed evidence for this checkpoint

Final integrated command results are recorded below after completion. Log paths refer to this disposable workspace and are not durable release evidence unless preserved with the review artifacts.

- `scripts/check.sh` completed successfully: 360 backend tests (113.924 s), 200 frontend tests, lint, web build/bundle budgets, the actual API-to-React stock regression, five local HTTP workflow tests, and a 6,403,051-byte complete-backup HTTP round trip in 13 chunks with retained-evidence hashes preserved. Native contract check: 256 routes, zero unmatched. Nine backup-target tests, 32 mocked VPS-management tests, and simulated database backup/transactional-restore safety checks passed. `/tmp/apex-integrated-check.log`.
- The script explicitly skipped encrypted-backup safety tests because `age` and `age-keygen` are absent. A successful aggregate exit does not close that test gap. Simulated activation messages in the log are mocked test output, not production actions.
- Disposable PostgreSQL 17.11: 18 concurrency tests, 100 reconstructed regressions (including journal-source tests), five HTTP workflow tests and a bounded eight-client workload passed. Twenty invoices, twenty partial receipts, two expenses, two stock-return notes and ten replays produced zero errors. Evidence directory: `/tmp/apex-postgres-integrated-final`; runner log `/tmp/apex-integrated-postgres.log`. This is consistency evidence, not production load capacity or actual-database recovery proof.
- Remote PR59 was fetched read-only and `git diff d66c544 FETCH_HEAD` was empty. At product checkpoint f29787f, 19 local commits followed d66c544 and 29 followed the recovered PR56 base. No remote mutation occurred.
- Current-source full Windows/Android builds, CI browser/device jobs and physical-device acceptance were not run in this checkpoint. Prior compiled native helper evidence remains valid for unchanged sources but is not a substitute. Final-CI publication remains unattempted; there is no new upload denial or uncertain upload outcome to report.

### Follow-up: encrypted backup and reopened lifecycle blockers

The previously skipped encrypted-backup test subsequently passed using Debian's authenticated age 1.2.1-1+b5 package, extracted under /tmp without installation. Durable provenance, package/script hashes and scope are in [encrypted-backup evidence](evidence/encrypted-backup-2026-11-12.json). Real encryption/decryption was exercised; database and remote storage remained mocked. This closes the local missing-tool test gap, not production recovery verification.

Independent review then reproduced two lost lifecycle protections in candidate 9159cbf: a settled return note could be dated after its refund, and an original payment used when issuing return credit could be cancelled. Accordingly that candidate must not be released. The subsequent correction and its test results are recorded below; all other browser/native/production gates remain open. Parent-browser observations on 9159cbf passed sampled high-zoom drawer navigation, invoice totals/trails, repeat-return defaults, state/date hints, party filters and stock details. These are sampled observations reported by the independent reviewer, not exhaustive final-commit acceptance.

The lifecycle reconstruction is described in [SETTLED_RETURN_LIFECYCLE_RECONSTRUCTION.md](SETTLED_RETURN_LIFECYCLE_RECONSTRUCTION.md). It closes the two reproduced write-path gaps and adds restore rejection for excess return credit without retained source capacity, subject to final test/review results. It does not close the remaining original-lost-fix inventory or justify declaring the app release-ready.

Lifecycle correction final evidence: 366 SQLite tests; 18 PostgreSQL concurrency tests, 106 PostgreSQL regressions, five HTTP workflows and bounded zero-error workload passed. No frontend/native code changed in this correction. The prior 9159cbf branch remains an immutable historical checkpoint; review the new correction commit before release consideration.

## Post-checkpoint corrections requiring independent review

The immutable `9159cbf` candidate is blocked by subsequently reproduced settled-return lifecycle defects. `9db279c` reconstructs those guards: 366 backend tests and disposable PostgreSQL 18 concurrency/106 regression/five HTTP tests passed. A real age 1.2.1 encrypt/decrypt backup safety test also passed using a verified Debian package; see `SETTLED_RETURN_LIFECYCLE_RECONSTRUCTION.md` and `evidence/encrypted-backup-2026-11-12.json`.

`41ef08e` improves party report PDFs with explicit scope, opening/closing balances, INR formatting, human-readable types and embedded fonts. Seventeen targeted tests and all nine rendered proof pages passed inspection. These PDFs are searchable, but are not tagged/PDF-UA certified.

The native PDF/share follow-up is documented in `NATIVE_PDF_SHARE_REVIEW.md`. Compiled request/helper tests do not close the full native build, device, PdfRenderer or TalkBack gates. All these changes remain local; the old checkpoint and earlier CI must not be represented as covering them.

The subsequent critical-reconstruction pass found and corrected missing XLSX formula/text fidelity protection. It also confirmed that party casefold identity and native access-denial cache handling remain incompletely reconstructed; see `CRITICAL_RECONSTRUCTION_INVENTORY.md`. These gaps prevent declaring the reconstruction complete despite passing targeted suites.


## Current native follow-up reconciliation (2026-11-12)

The earlier matrix is historical evidence, not a declaration that the current tree
has passed a full release run. Through `66dce6e`, independent reviews have confirmed
the targeted native transport, picker/export, PDF/report, retained receipt/recovery
and statement-preview fixes. The subsequent Android import snapshot correction is
local and awaits independent review. No percentage-complete or delivery date is
supported by the remaining acceptance gaps.

| Area | Completed evidence | Unresolved dependency / acceptance |
|---|---|---|
| Windows/Android session and revocation | Compiled actual transport/ownership methods; independent delayed-success/failure reviews | Full app login, expiry, same-token replacement, offline and process-death device flows |
| Native PDF/report/file export | Actual callback and save/print/share boundary harnesses with synthetic launchers; independent review through 654f7f4 | Real WinUI/Compose rendering, OS picker, external viewer, print and share UI |
| Receipt/recovery data | Independent c0f4d2b and 66dce6e checks: 32 Android ownership/selection cases and Windows code/download cases | Real attachment selection/error/retry and recovery-code lifecycle; no real secrets used in tests |
| Native import | Windows seven actual preview callback cases independently passed; Android 11 production request-gate cases passed locally | Android full callback/UI acceptance and all native import commit/lost-response/restart paths; old previews no longer acquire edited option identity |
| Web visual | Parent observed sampled 9159cbf invoice/return, GST, stock, zoom/reflow, import, backup and role flows | Repeat relevant scenarios on final SHA; exhaustive feature and screen-reader matrix still incomplete |
| Accounting/API | Prior lifecycle, restore, numerical and PostgreSQL evidence remains in earlier sections | Fresh complete integrated regression run and historical read-only audit on an authorized snapshot |
| Native full builds | Portable C#/Kotlin methods compile | Android SDK plus AGP 8.13.1 dependency resolution; Windows SDK/WinUI runner; exact-SHA CI artifacts |
| Production activation | No production action performed | Verified full backup+objects+keys restore, migration rehearsal, all-writer pause, rollback/forward recovery; user owns deployment |

The Android import correction binds file/preview reads to an original access and
input revision, rejects duplicate preview work, preserves the old selection on
failed replacement, and records the preview's starting options rather than options
edited during the request. The harness exercises the production request gate with
synthetic delayed operations and checks source wiring; it does not compile Compose
or prove the entire UI callback. Native full-build and real-device gates therefore
remain open even when these targeted checks pass.

### Day book conversion labels follow-up

The exact-10fcf92 browser audit identified non-posting source documents labelled
as drafts after conversion. Day book now reports company-scoped conversion status;
all three clients show converted/non-posting/unposted distinctly. Cancelling a
converted target reopens the source as non-posting. Existing posted/cancelled flags
and financial totals are unchanged. Recognized cancellation journals display
Original posting / Cancellation reversal plus voucher number; raw references remain
in the API, with a collapsed technical-reference disclosure on web. Manual journals
retain their entered reference.

Validation: ten backend Day book/trail tests and nine rendered everyday-feature
checks passed, plus frontend lint/build/bundle budgets. Native display edits are
source-reviewed only: temporary Kotlin/.NET toolchains were lost in the environment
reset, and full native builds remain open. The disposable Python environment was
recreated from repository requirements. This follow-up supersedes 10fcf92 for product
acceptance; it has not been published. The previous GitHub blob upload was denied
by automatic review and was not retried or bypassed.


### Restored Kotlin compilation evidence

Restored temporary Gradle 8.14.3 from the official downloads.gradle.org distribution;
SHA256 matched `bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531`.
At product revision 9ad0079, AndroidRetainedRead passed 32 cases and
AndroidImportSnapshot passed 11 cases again. A new harness compiles seven actual
DayBook status/reference expression cases and is wired into CI. This establishes
expression/helper compilation, not a full Compose build or device behavior.

The attempted offline `:app:compileDebugKotlin` still fails during plugin resolution:
`com.android.application` 8.13.1 is absent from cache. No application compiler result
is available. Log: `/tmp/apex-restored-android-build.log` (disposable environment).
Windows SDK/.NET toolchain restoration and full WinUI builds remain outstanding.
Source inspection found the Android workspace removes DayBookScreen when
recordsReady is false; no additional retained Day book access defect was established.
The parent independently passed the preceding status fix, including restore and
company-isolation probes. No publication retry, device permission change or
deployment was performed.

### Day book document keyboard action

A rendered regression reproduced the absence of any focusable document-opening
control in Day book. Document numbers now use named native buttons when the source
record and callback are available; missing records and journals have no dead action.
The table row itself is no longer a mouse-only action. The test failed before the
change (zero controls instead of one), then all ten everyday-feature tests passed,
along with lint, web build and bundle budgets. JSDOM verified focus and activation;
real keyboard navigation and screen-reader/browser acceptance remain separate.
No accounting/API mutation, publication retry or deployment was performed.

### Previous-price identity and recovery follow-up

Rendered synthetic testing exposed actionable old price choices while a different
party's request was pending. Previous prices now binds data, errors and Apply actions
to the company/party/item/side request generation, including switch-away/back and
unmount invalidation. Failed reads have an announced error and an explicit Retry
prices button. Twelve everyday-feature tests passed (including party changes,
company/item/side changes, stale errors, failed reads and successful retry), plus
frontend lint/build/bundle budgets. This is rendered component coverage, not a real
browser/device or financial posting acceptance claim.

Day book's focusable button also preserves display_number when a future non-journal
response provides it. Current backend only supplies display_number for journals;
this is defensive compatibility, not a demonstrated current backend regression.
No financial records were changed. Publication remains denied and was not retried.

### Day book error and retry follow-up

A rendered failure reproduced an unannounced error while the header continued to
say Loading. Day book now announces errors, displays an unavailable state and offers
Retry day book without changing the selected date. A record refresh invalidates old
totals while awaiting its new result; failure cannot leave obsolete figures looking
current. Obsolete company failures remain suppressed. Fourteen rendered everyday
feature tests passed, including failure/retry, stale totals and company switching;
frontend lint/build/bundle budgets passed. Browser/screen-reader acceptance remains
open. No financial/API write, publication retry or deployment was performed.

### Reorder quantity feedback

Selected invalid/empty order quantities previously disabled Review without linked
field feedback. Reorder now marks the field aria-invalid and links a plain-language
quantity requirement. Correcting the value removes both invalid state and error
association; the existing positive/three-decimal validation rule and reviewed payload
are unchanged. Fifteen rendered everyday-feature tests passed, including a selected
zero recommendation corrected to 1.234, plus lint/build/bundle budgets. No real
browser/screen-reader, native UI or posting coverage is claimed for this small fix.
Publication remains paused; no denied upload was retried.

### Commerce money submission ownership

The full frontend suite passed 230 tests at 7bd94d6 before this follow-up. A new
rendered probe then reproduced two money-form send calls from duplicate submit events.
The form now uses a synchronous in-flight guard, disables its fields while pending,
retains inputs on failure, and suppresses completion after unmount. The parent keys
the form by company/connection and only refreshes the original active store after
its command completes. Eleven accounting-safety rendered tests passed, including
double submit, close, switched-store completion and error/retry, plus lint/build
and bundle budgets. All sends were synthetic; no real integration was contacted.
This proves duplicate UI dispatch prevention, not a reproduced duplicate accounting
posting (server command IDs already provide a separate idempotency boundary).
Other commerce mutations, process-death/unknown-outcome recovery and real-browser
acceptance remain separate audit scope. Publication was not retried.

### Confirmed commerce command versus failed refresh

A synthetic accepted command followed by a failed workspace read previously surfaced
as submission failure and retained the filled form. Money commands now complete the
form after confirmed acceptance, while a separate alert tells the operator to refresh
delivery results without queueing again. Current-store ownership still gates that
alert. The explicit Refresh action also no longer performs a redundant second read.
Twelve accounting-safety rendered tests passed, including one POST plus failed GET
and GET-only recovery; lint/build/bundle budgets passed. Unknown POST outcomes and
process-death recovery are not reclassified as success by this change. No integration
server, financial books, publication or deployment was touched.

### Commerce uncertain-response payload recovery

Unchanged retries already reused a command ID, but edits after an uncertain response
could create a new intent/key. The money form now freezes the original operation and
payload for unknown/network, 408, 409 and 5xx outcomes, disables new input, and offers
Retry original source command. Definitive rejection (tested 422) permits correction.
The parent retains recovery objects in memory per company/connection path so switching
stores and returning within this mounted workspace preserves the original payload
and command ID. Confirmed completion clears recovery even if the form has closed.
Seventeen rendered accounting-safety tests passed, including attempted edits after
uncertain outcomes and store-switch recovery; lint/build/bundle budgets passed.
These are synthetic commands, not a live Bagisto or posting acceptance run. Recovery
is not persisted through workspace unmount, browser reload, sign-out or process death;
operators must reconcile delivery history in those cases. No publication retry or
deployment was performed.

### Shared commerce recovery and durable-recovery assessment

Independent review found a remount-before-response race in cb09e7f. Shared recovery
is now observable, including its single-flight state; reopened forms see success,
definitive failure or unresolved original payload without issuing duplicate commands.
Twenty targeted rendered tests passed, plus a synthetic backend test proving the
latest-200 outbox window is not authoritative absence evidence. See
COMMERCE_RECOVERY_BOUNDARIES.md for exact limits and durable recovery prerequisites.
No financial payload is persisted in browser storage; reload/sign-out replay remains
unimplemented. Final lint/build/bundle budgets passed. No publication retry or deployment was performed.

### Commerce recovery warning across tabs

A rendered regression showed the recovery warning disappeared when Payments closed
while its request remained unresolved. Other tabs now show the current store's
in-flight/uncertain status, original reference and a direct return to Payments.
The money form also explains reload/sign-out/workspace-exit limitations before
submission. Twenty rendered tests passed, including notice removal on success or
definitive rejection and retention on unknown outcome; lint/build budgets passed.
No persistent payload storage or automatic replay was introduced. Real-browser
acceptance remains open; no publication retry or deployment.

### Commerce obsolete read responses

Synthetic delayed transport tests reproduced three failures: an old company's
connection list replaced the current company's list when transport ignored abort;
its late error also surfaced in the new company; and a prior store workspace error
surfaced after switching stores. Connection success/error handlers now check their
abort ownership, and workspace failures use the same request-generation guard as
successful reads. Twenty-four rendered tests passed (three newly red cases now
green, plus stale workspace success control). Lint/build/bundle budgets passed.
This covers read completion ownership, not every commerce mutation callback or
real-browser acceptance. No production access, publication retry or deployment.

### Commerce mutation dispatch and completion ownership

A synthetic same-turn double click dispatched two history commands before rerender;
a synchronous per-context action flight now prevents duplicate dispatch. Generic
mutation success/failure/refresh completion is scoped to its original context and
lifetime. Connection creation and order-action callbacks check ownership before
changing setup/order state. Context changes clear obsolete busy/notice state.
Twenty-eight rendered tests passed, including current one-time setup completion,
duplicate dispatch and late company-change success/failure. The company prop-reuse
cases are defensive component tests: main normally keys this view by company ID,
so they are not proof of a production cross-company leak. Lint/build budgets passed.
Unknown outcomes for non-money commands and same-context order-dialog replacement
remain separate audit work; this is not a complete commerce acceptance claim.
No production access, publication retry or deployment was performed.

### Order-dialog ownership and uncertain command recovery

Reproduced order A's late success closing newer dialog B within the same store,
and unknown responses leaving new order commands enabled. Dialog generation now
guards closing, while per-store observable recovery freezes original order commands
and exposes exact retries. Accepted commands remain accepted if only refresh fails.
Thirty-six rendered tests passed, including invoice/cancellation success, unknown,
422 and post-success read-failure cases. Lint/build/bundle budgets passed.
Recovery remains memory-only; non-command setup mutations and actual integration
delivery remain separate gaps. No real store commands, publication or deployment.

### Connection creation uncertain response

Synthetic tests demonstrated the UI allowed another creation submit after unknown
response. It now locks the original setup and provides a read-only connection check;
existence does not recover the one-time credential, absence does not authorize replay.
Thirty-nine rendered tests passed, including found/not-found recovery and corrective
422 behavior. One isolated backend test passed for duplicate constraint, single-row
result, secret-free lists and company isolation; no external store was contacted.
Lint/build/bundle budgets passed. Secure credential recovery remains unimplemented,
and the local warning/lock is memory-only. No publication retry or deployment.

### Integrated frontend and repeat state-change verification

At ee1182d the complete frontend suite passed: 261 tests. This is rendered/synthetic
coverage, not browser/device certification. A separate synthetic backend probe
reproduced repeated Active PUTs incrementing version and queuing another stock
projection after the state was already active. Matching-state PUTs now return the
public connection without new timestamp/version/projection/audit mutations, after
existing authorization and activation validation. A true Paused-to-Active transition
still performs its normal projection. All 18 commerce backend tests passed, including
this regression and existing lifecycle cases. No external store worker, production
access, publication retry or deployment was used. PostgreSQL concurrency and actual
store delivery remain separate acceptance gates for this change.

### Committed activation response metadata

Independent review found genuine transitions returned pre-update version/timestamp.
The endpoint now reloads the scoped committed row before building its public response.
All 19 commerce backend tests passed, including four concurrent SQLite activations
(one projection) and four concurrent no-op repeats (no further mutations), with
response metadata checked against committed storage. PostgreSQL remains unverified.
No external store calls or production actions were performed.
