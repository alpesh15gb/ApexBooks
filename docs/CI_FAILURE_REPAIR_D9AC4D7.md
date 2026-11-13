# CI repair for d9ac4d7

Base: d9ac4d76ce246ddbd049a0b50a19fd561a617390. Synthetic verification on 13 November 2026; no publication or production changes.

## Changes

- Constrain document metadata selects to their grid column. The original CI trace shows the place-of-supply selector overflowing the 390px Purchase bill form. No browser assertion was removed or relaxed.
- Disable individual Windows PDF toolbar buttons on read-access invalidation, rather than assigning nonexistent StackPanel.IsEnabled. Continue clearing retained bytes, image and controls and guarding forced callbacks.
- Correct the Windows fixture: Panel no longer inherits Control. Add an assertion that all retained toolbar buttons are disabled after denial. This fixture reproduces CS1061 on the original base and passes the repaired method.
- Restrict AndroidCoreRefresh extraction to the production refresh method. Adjacent finishConfirmedImport and finishConfirmedEntry remain exercised by their dedicated compiled suites, which already run in CI. No Android production behavior changed.

## Verification

- Aggregate scripts/check.sh passed after restoring pinned Python dependencies: 449 backend tests, 495 frontend tests, lint, build/bundle budgets, stock overview, isolated HTTP/complete-backup checks, 256 native routes, deployment helper tests and simulated backup safety. Encrypted backup tests explicitly skipped because age/age-keygen were absent. Initial attempts without project dependencies failed and are not counted as successful runs.
- Full isolated browser command passed using desktop Chromium: run_local.py --presentation --business --accessibility --browser-executable /usr/bin/chromium. Includes the unchanged 390px Purchase bill assertion, 122 presentation accessibility scans, keyboard journeys, business accounting and nine-line quotation conversion. Visual inspection confirmed the repaired dropdown stays inside its column. Initial command-runner Chromium launch failed with socket Operation not permitted; the supported desktop terminal environment ran the suite without changing security settings. Owned servers stopped and disposable database removed.
- Compiled AndroidCoreRefresh (mixed denial, transient failure, stale context, success), AndroidImportCompletion and AndroidEntryCompletion passed, including completed-write notices and stale-session cases. Official Gradle 8.14.3 distribution checksum verified.
- Compiled WindowsPdfOwnership and external share/print tests passed using official SHA512-verified .NET SDK 10.0.100. Baseline negative control fails with the same CS1061. These use synthetic WinUI/rendering/OS boundaries.
- Full Windows Debug and Release attempts on Linux stop with NETSDK1100; they are NOT passing full builds. Windows CI Debug/Release, unsigned package and UI smoke remain required. Android full app/device checks were not repeated locally. New-commit GitHub CI has not run.

## Evidence

External local evidence (not product assets): /workspace/shared/apex-ci-browser.log, /workspace/shared/apex-ci-browser-evidence/, /workspace/shared/apex-ci-native.log, /workspace/shared/apex-ci-aggregate.log. Original GitHub artifact 13989389167 from run 43320653549 was downloaded and verified against SHA256 d3db0d1c2ae5ed06a1ed3dd85122870bbf6b0fb0e276a12f2b77384ffb323353 before inspecting its trace.

Publication remains paused under the prior automatic-review denial; no alternate publication route was attempted. No merge or deployment. This repair is not statutory or device certification; known Indian-script PDF glyph/shaping limitations remain outside this batch.
