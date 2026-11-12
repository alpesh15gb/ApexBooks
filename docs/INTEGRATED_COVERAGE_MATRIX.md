# Integrated candidate coverage and release gates

This is a review candidate, not a production-ready declaration or a claim of comprehensive Indian accounting/GST compliance. The user owns deployment. No production data, credentials or systems were accessed for this checkpoint.

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

- Backup unencrypted acknowledgement checkbox layout still needs alignment/visual acceptance.
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
