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

### Commerce order dialog keyboard integration

The actual DialogFocus manager did not recognize the custom commerce dialog: a
rendered test reproduced focus staying on its background opener. The dialog now
registers as a focus surface and labels its Close control for shared Escape handling.
All 42 targeted frontend tests passed, including initial focus, background inert,
Tab wrap, Escape and opener restoration plus commerce workflow regressions.
Lint/build/bundle budgets passed. This is JSDOM coverage, not real-browser or
screen-reader acceptance. No publication retry or deployment was performed.

### Keyboard access to uncertain order recovery

Testing the active focus trap with an uncertain cancellation found the retry control
outside the dialog's keyboard boundary. The existing recovery notice now renders
inside an open order dialog and returns to the workspace when it closes. One notice
and one exact-retry action remain; changing placement sends no command. All 43
focused frontend tests passed, including the new actual-manager integration repro,
plus lint/build/bundle budgets. Real browser/screen-reader acceptance remains open.
No production access, publication retry or deployment occurred.

### Archived-item checkout and reservation numeric validation

Synthetic signed requests reproduced new checkout reservations accepting archived
tracked and untracked items. New reservations now require an active item; exact
replays of reservations accepted before archival retain their existing identity.
Reactivation permits a corrected new request. No existing reservation is changed.
Eight malformed quantity cases (NaN, infinities, zero, negative, excess precision,
excess magnitude and invalid text) already rejected atomically and allow corrected
same-reference retries; these behaviors now have explicit regression coverage.
All 23 commerce/item-identity backend tests passed. This batch does not alter store
catalogue visibility or claim acceptance of already-open orders after archival;
real-store delivery and PostgreSQL remain separate gates. No external store calls,
production access, publication retry or deployment occurred.

### Archived-item sellable stock projection

A synthetic tracked item with book stock 10 and an existing hold of 1 still reported
sellable 9 after archival. Stock/workspace projections now expose is_active and zero
available_quantity for archived items, retaining actual book quantity and reservations.
Reactivation restores computed availability (9 in the fixture). A mocked worker call
verified the outbound projection also carries zero; all 24 commerce/item-identity
backend tests passed. No real delivery occurred. This does not change website product
visibility, manage_stock flags or existing orders. Untracked products may remain
listed in Bagisto; the authoritative new-checkout archived-item rejection still
applies. Real-store and PostgreSQL acceptance remain open. 9ad0079 remains in HEAD
ancestry; its Daybook conversion-status visual recheck remains on the final matrix.
No publication retry or deployment was performed.

### Projection retry across archival

Added a synthetic worker lifecycle regression: freeze a positive-stock projection
on a simulated lost response, archive the item, deliver its newer zero-stock
projection, then retry the earlier packet. The retry retains its exact command and
payload; the newer projection has a higher version, and book stock is unchanged.
All 23 commerce tests passed. No new API/worker defect was reproduced. The final
stale_projection result was mocked; this verifies local packet ordering/retention,
not actual Bagisto execution. Source inspection confirms the bridge's older-version
ignore rule and whole-unit stock restriction; full bridge integration remains open.
No production access, external delivery, publication retry or deployment occurred.

### Report export scope during delayed download

Returned to the visual-audit backlog rather than adding projection-only tests.
Rendered export tests reproduced files saving after company/date changes, returning
to the report library, and unmount. Exports now capture the report context generation
and check it after body consumption, with a final session check immediately before
the download side effect. Obsolete failures are suppressed; current errors remain.
All 51 targeted frontend tests passed (12 report-export scope cases plus 39 workflow
cases), including company-away-and-back. Lint/build/bundle budgets passed. The save
sink was mocked; actual-browser export acceptance remains open. The newly reported
same-day party-statement chronology issue is queued separately. Full native builds,
device acceptance, real Bagisto delivery and production recovery gates remain open.
No production access, publication retry or deployment occurred.

### Same-day party statement chronology

Reproduced reference sorting placing a same-day credit note before its source invoice
and receipt. Party reports and party ledgers now sort by date and retained entry
created_at timestamp, then deterministic reference/type/party/amount tie-breaks.
Missing timestamps follow recorded entries, with explicit unknown-history disclosure;
no accounting balance formula or stored book entry changes. JSON includes the ordering
note/timestamp, UI displays the note, XLSX retains row order and adds Report notes,
and PDFs include the disclosure. Twelve backend and 53 frontend tests passed, plus
lint/build budgets. Synthetic invoice/receipt/credit rows run 100→75→25, and JSON/
XLSX/PDF order remains stable through six restores covering recorded, tied and missing
timestamps. Existing ledger, multipage PDF and cash-book tests passed. This is not
proof of historic posting order when timestamps are absent/tied, nor final browser
or screen-reader acceptance. No publication retry or deployment occurred.

### Service versus physical inventory boundary

Actual synthetic API tests confirmed services could be stock-tracked and receive
opening inventory, and tracked goods without movements could become services.
This application does not model service WIP/capacity accounting; goods-only physical
stock tracking is an application scope decision, not a general statutory assertion.
New masters/imports and tracked-goods-to-service changes now reject this combination.
Legacy service-stock metadata remains editable, existing journals are not rewritten,
and legacy backup preview remains supported. New service stock openings reject;
no-history legacy classification can be corrected explicitly to goods. Web forms
explain the boundary and opening-stock choices exclude services. All 20 backend and
27 frontend focused tests passed, plus lint/build budgets. API validation applies to
native requests too; native UI/device acceptance and broader legacy-stock correction
work remain open. No publication retry or deployment occurred.

### Remaining incoming visual findings, prioritized

- Financial statement PDF/XLSX exports must carry the UI's actual calculation basis,
  limitations and accountant-review warning, plus explicit INR; preserve numeric cells.
- Inline journal/account draft loss on navigation/company change; announce validation.
- Clear stale form-local access-denial wording only after verified recovery, retain draft.
- Cash-book PDF readable labels/dates/currency and multi-page checks; announce invalid range.
- Document discount preview error should identify the 0–100 document-discount field.

### Report export basis and currency (after 5f49c9d)

P&L/balance-sheet PDF and XLSX now retain the posted-ledger basis and the explicit
uncalculated depreciation/NRV/accruals and accountant-review warning. Ageing exports
retain document-date ageing and manual-adjustment limitations. Selected report PDF
exports identify INR, use readable transaction labels/dates, Indian amount grouping,
right-aligned amounts, embedded report fonts and repeated scope/currency/page footers.
Cash-book ordering disclosure moves into report notes rather than a transaction row.
XLSX retains numeric monetary cells, INR headers and a Report notes sheet; underlying
Type identifiers remain unchanged in XLSX. UI uses the same server basis text, and
cash-book errors are exposed as alerts.

Validation: 15 backend tests (report export basis, statements, party ledger and party
chronology), 51 frontend accounting-safety/export-scope tests, lint and production
build/budgets passed. Visually inspected all five pages across populated statements,
three-page ageing and cash-book samples; no clipping observed. Empty reports and
numeric JSON/XLSX parity are covered. These are synthetic tests, not browser/OS print,
screen-reader or statutory acceptance. PDFs remain untagged. Journal/account draft
preservation and stale recovery wording remain next priorities. No production access,
publication retry or deployment.

### Ledger drafts and verified access-recovery wording (after 4dd8067)

Ledger account/journal drafts now live in App-owned, company-scoped memory across
screen unmounts and company switches. Successful posting clears only the posted form;
validation and uncertain-result warnings retain the draft. No draft data is written
to browser storage. Reload prompts while drafts remain, sign-out confirms discard,
and signed-out state clears the cache. Pending ledger mutations register with the
existing navigation guard and synchronous duplicate-submit guard. Ledger errors are
alerts. Viewer roles cannot render/write the retained forms; editor recovery resumes.

MasterForm clears only an identified company-access error after the App completes
membership/record recovery. Drafts and unrelated validation errors remain; obsolete
access errors from an earlier recovery generation are ignored.

Validation: 13 rendered/synthetic tests passed, including actual Ledger component
remount/company isolation, viewer/editor transitions, same-account validation,
duplicate submit, separate account/journal clearing, uncertain-result preservation,
actual App master and stock recovery, and unrelated-error preservation. Lint and
production build/budgets passed. Full browser navigation/confirmation and assistive
technology acceptance remain open. Drafts are intentionally memory-only; no automatic
reposting or durable unknown-outcome recovery was added. Backend permissions remain
authoritative. No publication retry, production access or deployment.

### Journal unknown outcomes, party export scope and discount feedback (after cb18b80)

Independent review reproduced journal uncertainty being overwritten by unrelated
account failure, and a changed-reference retry after unknown outcome. Uncertainty is
now retained per operation and original command. Unknown journal commands freeze the
editor; normal submission is blocked and explicit retry uses the original immutable
values/reference. A company-scoped exact-reference lookup can confirm a matching
manual journal (date, memo, accounts and amounts) and clear the draft. Missing or
mismatched results remain unresolved, including a duplicate-reference 409. No absence
claim is inferred from a history list. The API filters reference in SQL and retains
company authorization; database reference uniqueness prevents identical retries from
creating another journal. Unrelated account/reversal/read errors cannot clear the
journal uncertainty. Account/reversal uncertainty banners remain distinct; their own
full frozen-command recovery remains a separate coverage gap.

Party statement modal exports had nine failing synthetic stale completion cases.
Company, party, date, away/back and unmount now invalidate delayed downloads/errors;
current results still download once, and session ownership is rechecked before save.
Document-discount validation now identifies the 0–100 percent/two-decimal field in
preview and create. Existing rounding/calculation behavior remains unchanged.

Validation: 28 frontend tests passed (ledger draft/recovery, App master recovery,
party export and report export scopes). Twelve backend tests passed (exact-reference
lookup/auth/company isolation/unique retry, invalid-discount atomicity and boundary
preview/save parity, purchase-return residuals). Lint/build/budgets passed. Synthetic
requests and fake download sink only. Browser/native acceptance, PostgreSQL concurrent
journal recovery and durable recovery across reload/sign-out remain open. Drafts and
uncertainty are memory-only; no production access, upload retry or deployment.

### Account/reversal frozen recovery and PostgreSQL (after d721f72)

Unknown account creation and journal reversal now freeze their original commands.
Normal/changed submissions are blocked; explicit retries use the original code or
journal ID/reference/date/reason. Recovery survives screen remount/company switching
in company-scoped memory and is unavailable to viewers. Account lookup filters exact
code in SQL; reversal lookup requires the original journal's reversal lineage plus
matching date/reason/reference. Missing, conflicting and 409 outcomes stay unresolved.
Uncertainty alone marks the workspace dirty for reload/sign-out warnings. No automatic
retry, destructive reset or durable storage of draft data was added.

Validation: six rendered tests passed, including account/reversal lost responses,
double submit, changed code, remount, company/role boundaries, original-only retry and
missing/conflicting/matching result checks; existing journal and master recovery tests
also passed. Four SQLite tests passed (three concurrency scenarios and reference lookup).
Lint/build/budgets passed.

A fresh official Debian PostgreSQL 17.11 toolchain was downloaded and SHA256-verified,
extracted under /tmp without system installation. Disposable loopback-only PostgreSQL
ran all migrations and three HTTP concurrency tests: four same-code account creates
(one 201, three 409), four identical-reference journals (one 201, three 409), and four
different-reference reversals of one original (one 201, three 409). Exact lookup matched
the winning result and reversal returned trial-balance totals to zero. The server was
stopped in a finally block. Evidence: evidence/manual-recovery-postgres-2026-11-12.log.
The environment disallowed Unix sockets; loopback TCP worked when server and tests
ran in the same execution namespace. This is bounded synthetic consistency evidence,
not load testing or production recovery validation. Browser/native acceptance and
memory loss across reload/sign-out remain open. No upload retry or deployment.

### Opening balances and credit settlement refresh recovery (after 70ae985)

Synthetic rendered tests reproduced two immediate opening-balance requests and
confirmed writes left looking unsaved when the subsequent balance refresh failed.
Opening balances now use the existing original-operation/idempotency-key retry holder,
with synchronous flow guard, locked pending fields and navigation registration. Owner
and credit-write role checks also run in handlers. The opening component is keyed by
company. Credit retries remain reachable if a refreshed record list removes the
exhausted note: the frozen original request is used, not a reconstructed missing-note
request.

Both forms clear submitted fields/rotate the key only after confirmed POST success,
retain a visible success message, and report refresh failures separately. Refresh
balances performs only the read callback, with single-flight guarding. App wiring
turns loadRecords' missing result into an explicit refresh error; it does not falsely
report successful refresh after a swallowed read failure.

Validation: nine frontend tests passed, including both rendered failure/retry flows,
missing-note recovery, frozen payload/key and read-only refresh recovery, plus posting
registry/navigation tests. Four backend SQLite tests passed: original-key opening and
credit-refund replays return the same record; changed payloads reject without changing
records/trial balance; existing opening restore and credit settlement lifecycles pass.
Lint/build/budgets passed. No backend posting rules changed. Actual browser/native
acceptance and durable reload recovery remain open. No production, publication retry
or deployment.

### Advance recovery and settlement access-loss retention (after 96b2207)

Seven synthetic advance cases failed before the fix: an exhausted/missing source
removed the only frozen retry control, and stale report downloads/errors completed
after changing company/date or closing the view. Advance retries now remain reachable
for the original operation, confirmed success is separated from read-refresh failure,
and exports verify context/session before file saving. The opening/credit refresh
feedback helper is shared rather than duplicated.

Independent review found that recordsReady=false unmounted CreditSettlements on
access loss, discarding an uncertain command. Credit and advance forms now stay
mounted above that conditional in the company workspace. The access-loss overlay
still hides/locks the workspace. Records/balances clear, while the in-memory original
request survives. Viewer recovery displays unresolved status without write controls;
editor recovery retries the identical key/payload. Normal navigation remains blocked
while the registered operation is unresolved. This does not persist recovery through
sign-out, reload or process loss.

Validation: 21 frontend tests passed, including actual App revocation/recovery for
credit and advance as viewer/editor, original request identity, source exhaustion/
removal, export completion scope, prior opening/credit flows and posting-request
semantics. Four backend SQLite tests passed, including customer/supplier advance
refund replay with identical record ID, changed-payload rejection and unchanged books.
Lint/build/budgets passed. These are synthetic DOM/API checks; real browser/native
acceptance remains open. No production, denied publication retry or deployment.

### Period-lock unknown outcome and memory boundary (after 734654c)

Synthetic period-lock tests reproduced a lost-response save leaving the prior date
presented as current and allowing review cancellation. Unknown/time-out/server/conflict
outcomes now freeze the reviewed date, mark current state unverified, and register a
pending operation. Read-only Check current lock resolves only a verified date at or
beyond the reviewed date; an older date or failed read stays unresolved. Owner-only
explicit retry uses the original reviewed date and is single-flight. Viewer access can
verify current state but cannot retry the write. No backend locking rules changed.

Shared uncertain-posting and manual-ledger UI now explicitly discloses tab-memory-only
recovery and warns against reload/close/sign-out. An unresolved opening balance remains
visible after owner role loss, while retry requires owner access. The actual durable
boundary and interruption limits are documented in UNCONFIRMED_POSTING_RECOVERY.md;
this is disclosure, not an implementation of cross-session recovery.

Validation: 18 frontend tests passed, including old/failed/later lock reads, viewer
verification, original-date retries, double clicks, stale-company response protection,
opening owner/viewer recovery and existing posting/ledger recovery checks. Two backend
matrices passed covering posting-family period-lock enforcement and company write-role
restrictions. Lint/build/budgets passed. Real browser/unload prompts, native parity and
durable process-loss recovery remain open. No production, upload retry or deployment.

### Integrated frontend check and legacy encrypted export (after e9e013b)

The full frontend suite passed all 312 tests at e9e013b. Subsequent targeted review
reproduced eight legacy encrypted-backup completion failures: file creation or stale
errors after company/away-back, role, unmount or session change during encryption.
BackupRestore now captures ownership before download and checks context, session and
company access again after asynchronous encryption, immediately before file creation.
Current failures remain visible; stale-context/session errors are suppressed. The
restore mutation path was not changed by this batch.

Validation after the export fix: 17 tests passed, including 14 delayed crypto/download
cases plus three existing import/restore safety tests. Same-company access revocation
also blocks the final download. Tests use fake crypto completion and a fake file sink;
they do not prove browser download, encryption compatibility or device acceptance.
Lint/build/budgets passed. The full 312-test run predates this narrow export change;
no new full-suite claim is made. No production or publication retry occurred.

Next verified source-level gap to reproduce: web MasterImport still tolerates
post-quote characters and populated blank CSV headers; native strict parsing does not
by itself protect this separate web path. Legacy restore preview/file ownership also
requires a separate review; this batch only covers backup downloads.

### Web CSV and legacy backup preview follow-up (2026-11-12)

Strict UTF-8 decoding now rejects invalid bytes/NUL input. Master CSV parsing rejects
malformed quotes, duplicate normalized headers, populated unsupported/blank columns,
and inconsistent row widths before any preview request. Valid BOM, CR/LF/CRLF,
quoted commas/newlines and doubled quotes retain supported field contents; existing
field trimming/default semantics remain. Formula-like strings remain literal data;
this parser is not spreadsheet export sanitization.

Legacy restore preview captures company/role, session and access ownership before
file reads/decryption, verifies before dispatch and before accepting results, and
suppresses stale failures. Restore checks accepted preview ownership before a new
commit; unresolved original posting recovery remains unchanged. Late encryption
errors cannot appear after access revocation/recovery.

Validation: 60 focused frontend tests, 3 existing backend export-literal tests,
ESLint and production frontend build/bundle budgets passed. Synthetic rendered
components and fake file/crypto/network boundaries only; no real encryption or
browser-picker acceptance claim. Full native builds/device checks and memory-only
uncertain-operation durability remain open. Same-token session-generation concern
has not been demonstrated as a real flow. No production, upload retry or deployment.

### Legacy restore completion ownership (2026-11-12)

Synthetic delayed commit responses reproduced five stale callback/error failures:
a successful old restore could call onRestored after company changes, owner-role
away/back, or unmount; errors could appear in replacement contexts. Completion now
checks original context, session and access ownership before callbacks and feedback.
Current owner operations retain normal completion; no automatic second POST occurs.

Eight new rendered commit cases plus existing preview/export cases: 44 tests pass;
ESLint, production build and bundle budgets pass. This covers dispatch-to-completion
ownership, not context changes *inside* the parent's awaited onRestored callback.
That callback's loadCompanies/navigation ordering remains a follow-up inspection.
No real backup restore, production access, publication retry or deployment occurred.

### Parent restore navigation after refresh (2026-11-12)

Both legacy and complete backup callbacks now use onCompanyRestored. It captures
session, company/role workspace generation and access ownership before fetching the
company list, verifies after awaiting, then updates list/selection synchronously.
A stale read success/failure cannot navigate; a current failure propagates without
switching. A missing restored ID produces an actionable already-completed warning.
It does not call loadCompanies, whose swallowed error formerly allowed selection
without a successful refresh. Restores themselves are not reissued.

Validation: original callback extracted from main reproduced company B overwritten
by restored company. 27 tests pass: four actual rendered App handler cases (current
and switched workspace, successful/failed refresh), 15 helper ownership/list cases,
eight legacy commit cases. Actual App tests expose the real callback through a
build-only test seam, not a real file-picker or backup restore. Lint, frontend build
and bundle budgets pass. Native/device acceptance remains separate. No production,
publication retry, merge or deployment.

### Complete restore confirmed-result recovery (2026-11-12)

Reproduced: commit succeeds, parent company-list navigation fails, and the screen
has no direct action to open the confirmed result. CompleteBackup now retains that
company ID before navigation and offers Open restored company. Navigation failure
explicitly says restore completed and directs recovery of that existing result.
The open action uses the guarded parent callback and does not repost restore.

Validation: 32 tests pass across complete-backup, navigation helper and rendered
App cases. New regression failed before fix; it verifies one commit, retained result,
refresh-error feedback and double-click-safe reopen with no additional commit.
Lint, frontend production build and bundle budgets pass. Synthetic staged transfer
only; real encrypted ZIP, interruption/device and browser-picker acceptance remain
separate. No production, publication retry or deployment.

### Legacy confirmed-result reopen parity (2026-11-12)

The same confirmed-write/navigation-failure gap also reproduced in legacy restore.
It now retains the confirmed company result, shows an explicit already-restored
failure message and offers Open restored company. The action is owner-, company-
and session-scoped, single-flight, and calls only the guarded parent navigation
callback. It never repeats commit. Retained identity is memory-only.

Validation: 45 focused legacy backup tests pass, including the new red-to-green
confirmed commit / failed navigation / double-click reopen case. Lint, frontend
build and bundle budgets pass. Synthetic callbacks/files only; no actual restore,
production access, upload retry or deployment.

### Confirmed master import versus refresh failure (2026-11-12)

Reproduced confirmed import followed by failed record-list refresh showing a generic
error without read-only recovery. MasterImport now reports that import was confirmed,
keeps its completed preview, and offers single-flight Refresh imported records. App
wiring uses refreshPostedRecords so loadRecords' caught failure becomes observable.
The retry invokes only the refresh callback and does not repost imported rows.

Validation: 25 focused CSV/import tests pass, including red-to-green confirmed import,
failed refresh and duplicate-click retry (one commit). Lint, frontend build and
bundle budgets pass. No real imports or external access.

Remaining integrity boundary: masters/import has serialized, casefold-name duplicate
skipping but no durable operation receipt. Unknown commit outcomes and retries after
concurrent master renames need separate recovery design; duplicate skipping alone
must not be described as exact idempotent replay. This batch does not resolve that
boundary. No publication retry or deployment.

### Master import unknown-outcome investigation (2026-11-12)

Correction to earlier concern: API master renaming rejects with 422, so a supported
concurrent rename causing duplicate import was not reproduced. Active and archived
master unchanged retries create zero additional records; one unittest/two synthetic
lifecycle subcases pass. Name skipping still does not replay the original response
or bind an operation key to a payload. No duplicate-posting exploit is claimed.

See MASTER_IMPORT_RECOVERY_DESIGN.md for an explicit transactionally durable receipt
contract, migration/client capability boundaries and required SQLite/PostgreSQL
validation. This is a documented design, not completed receipt implementation.
No production access, publication retry or deployment.

### Durable master-import API receipts (2026-11-12)

Implemented optional keyed POST replay and actor/company-authorized GET recovery,
with canonical request hash and immutable original response/created IDs. Masters,
audit and receipt commit atomically. Changed payload/actor conflicts; legacy no-key
clients retain their response shape. Company backups omit receipts and restored
companies start a separate operation namespace. Migration i018fa586b03 refuses a
nonempty destructive downgrade; full database backup must include receipts.

Evidence: 22 SQLite tests pass (receipts, rollback-after-flush, legacy imports,
restore/capability compatibility and migration). Seven PostgreSQL 17.11 tests pass,
including four identical requests returning one result and four distinct requests
with one key yielding one success/three conflicts. PostgreSQL fresh migration,
empty downgrade/re-upgrade and nonempty fail-closed downgrade probe exits 0.
Disposable loopback databases only; server stopped afterward.

Remaining: capability-gated web/native adoption and reload recovery; no automatic
client protection claim. No production migration, publication retry or deployment.

### Capability-gated web master-import recovery (2026-11-12)

Web imports now adopt receipt keys only when advertised. Unknown outcomes retain
an original in-memory body and block changed/new commit; reload recovery persists
only key/kind/hash in actor/company-scoped sessionStorage. GET confirms the receipt;
missing receipt stays unresolved; original-file fingerprint enables same-key retry
without persisting CSV contents. Storage failure blocks initial POST. Legacy
servers receive no key and an explicit exact-recovery limitation.

Validation: 32 focused tests and all 406 frontend tests pass. Lost response/remount,
GET-only recovery, original-file mismatch, double-click retry, rejection before vs
after uncertainty, storage failure, actor/company isolation and legacy server
behavior covered. Lint/build/bundle budgets pass. No real browser or native UI
acceptance claim; closing the tab can lose its recovery reference. Native adoption
remains pending. No production, publication retry or deployment.

### Android master-import receipt adoption (2026-11-12)

Added capability-gated keys, app-private opaque restart references and GET recovery.
Original input fingerprint gates retry, capability/role loss blocks unsafe writes,
and unknown outcomes remain unresolved even after later rejection. Reference
creation is serialized across instances; no CSV or credentials persist.

Executed compiled Kotlin production-helper fixtures for restart/retry, corruption,
legacy compatibility, actor/company/origin namespace and four-instance races;
compiled actual save callback fixtures for unknown/422/success/role/stale-error;
and 11 existing import ownership fixtures. All passed. Full Compose build/device
acceptance and Windows adoption remain open. No production, denied upload retry or
deployment.
