# Exact-revision acceptance plan — no deployment

Product candidate: `10fcf9248aa38fd95206f6210988506bfe572d97`.
This plan is documentation only; its later commit does not imply a new product build.
Any implementation correction requires a new frozen product SHA and affected reruns.

## Observed state on 2026-11-12

- Local working tree was clean at the product candidate before writing this plan.
- Read-only GitHub inspection: draft PR59 head remains
  `fc415d654e0f1a4afd2c335a2b1202586ec1c695`; it does not contain the current stack.
- The connector returned no PR-triggered runs for the product candidate. Its lookup
  is first-page and PR-filtered, so this is not an exhaustive all-event run search.
- Available connectors inspect logs/artifacts and rerun existing jobs; no new-ref
  workflow-dispatch capability is exposed. Rerunning PR59 cannot test this stack.
- Local Android full build previously stopped before compilation because AGP
  8.13.1 was unavailable offline; Android SDK and Windows SDK/WinUI runtime are absent.
- No publication, merge, workflow dispatch, signing or production action is part of
  this plan. Any required publication approval must cover the actual current stack.

## Revision identity before accepting results

1. Preserve the existing bundle, verify its prerequisite `9b21ccce`, import into an
   isolated checkout, and check out the product SHA detached. Record `git rev-parse
   HEAD`, `git status --porcelain`, tool versions and artifact hashes with evidence.
2. If a review branch is authorized and published, verify its remote head against
   the intended SHA before opening/running the review checks. Preserve concurrent work.
3. Existing PR workflows use default actions/checkout: GitHub may check out a
   synthetic merge commit. Record that exact SHA and both parents. Such results are
   merge-candidate evidence, not exact-head evidence. For exact-head hosted checks,
   use an explicitly pinned checkout configuration before freezing the resulting
   candidate, or run the listed commands on an isolated runner checked out detached
   at the product SHA. Keep merge integration checks separately. Never relabel a
   merge result as head evidence.
4. Native build identities and API/web build identities must match the actual
   checked-out SHA. Save logs and screenshots with revision and scenario metadata.

## Required native build and acceptance jobs

| Check | Existing implementation | Prerequisites and result required |
|---|---|---|
| Android debug | check.yml android-client: unit tests, lintDebug, assembleDebug, HTTP journeys and ownership harnesses | JDK17, Android API36/build-tools36.0.0, accepted SDK licenses, Gradle/Maven dependency access; passing full compiler/lint/test logs |
| Android release compilation | native-release-checks.yml android-unsigned-release: lintRelease, assembleRelease, bundleRelease with apexUnsignedReleaseVerification | Same SDK/dependencies; successful shrink/resource compilation and unsigned-artifact verification; keep artifacts private, not a distributed release |
| Windows debug | check.yml windows-client: WinUI build, PortableClient/WindowsClient, callback/picker tests and streaming backup | Windows runner, .NET10, Windows/WinUI SDK and NuGet access; full build and test logs |
| Windows release compilation | native-release-checks.yml windows-unsigned-release | Unpackaged unsigned Release compilation and artifact hash; does not prove runtime acceptance |
| Windows UI | windows-ui.yml | Interactive Windows runner and loopback synthetic API; screenshots/logs from WindowsUi, then manual file/print/share/accessibility tests |
| Android emulator | native-device.yml | Currently intentionally skipped on ordinary PRs. workflow_dispatch plus allow_temporary_kvm_access=true is an explicit one-run permission-changing gate; do not enable without applicable authorization. Operator needs Actions dispatch access and an accepted published workflow/ref, or an approved existing emulator/device |

No signing key, production secret, SMTP credential or production account is required.
Hosted-runner dependency access and CI capacity are required. No automatic SDK-license
acceptance is proposed; current jobs fail if preapproved licenses are insufficient.

## Final integrated browser run

Run on the parent's working disposable browser desktop or a hosted isolated runner.
Use the exact detached candidate and a new disposable database; never reuse the live
API. The existing runner rejects external/reused API target variables.

```sh
python tests/e2e/run_local.py --browser --presentation --business --accessibility --artifacts browser-evidence
```

Prerequisites: Python dependencies, Node/npm-ci frontend dependencies, compatible
Playwright Chromium and permission to start owned loopback servers. Capture actual
API/web revisions first. Do not reuse older 9159cbf screenshots as final acceptance.

| Manual browser group | Required scenarios |
|---|---|
| Identity and access | Two synthetic companies; owner/editor/viewer; revocation while detail/editor/export open; recovery as viewer; cross-tab replacement/logout; draft preservation |
| Documents | Keyboard-only nine-line quotation/invoice, long descriptions, intra/interstate GST, invalid field focus, Save & new, lost response, partial settlement and repeat return |
| Reports | GST-month to ordinary report, company/party/date switches, failed/stale loads, displayed versus exported applied scope, cash-book ordering and party opening/closing |
| Integrity workflows | Cancellation and linked history, settled-note/payment rejection, stock opening/increase/decrease and provisional-cost return policies; no automatic historical repair |
| Files and import | CSV preview/commit with edits/errors/duplicates; retained receipt upload/download/hash/archive/restore; backup download, interruption/retry and restore into separate company |
| Reflow/accessibility | 1200px and 320px; roughly 303x199 CSS at 400% zoom; drawer, wrapped filters, modal scrolling, currency; focus return, Escape, announcements and screen-reader sampling |

For each scenario record pass/fail/not-run, exact revision, viewport/client, synthetic
fixture ID, observed result and evidence path. Fix failures, freeze a new SHA and
rerun affected scenarios plus full required build/check jobs. PDF text extraction
and portable tests do not replace visual, screen-reader or OS print acceptance.

## Dependencies that remain after CI

- Independent review of any subsequent findings. Parent review of 10fcf92 passed
  11 compiled import-gate cases and source wiring; full Compose flow remains unverified.
- Full native device UI matrix: file picker, print, share, failed fetch, offline retry,
  process death and accessibility; fake launchers establish no physical-device result.
- Complete final browser coverage and a fresh integrated backend/web/PostgreSQL run.
- User/operator-owned production recovery gates: full database+objects+keys restored
  into isolation, migration rehearsal, all-writer pause and verified recovery plan.
  This plan does not activate or deploy anything and gives no delivery-date promise.


## Safe work executed while preparing the plan

The PortableClient .NET10 suite completed successfully at product SHA 10fcf92,
including real client method tests for response ownership, old logout/401,
source-selection/retry, CSV validation and complete-transfer integrity. Synthetic
transport performance output is not a real network or device benchmark. The
working tree contained only this documentation change afterward. No hosted CI,
real device, production or external communication was invoked.
