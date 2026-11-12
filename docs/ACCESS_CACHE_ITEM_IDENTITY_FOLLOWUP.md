# Access-cache closure and item identity follow-up

Local batch after e46744f. No publication or deployment.

## Verified fixes

Two synthetic API cases returned 200 before this batch: a casefold-equivalent free-text line bypassed a tracked item selection requirement, and another bypassed an archived untracked item. Both now reject atomically using company-scoped casefold matches; explicit valid tracked item selection remains supported. Twenty-three focused item/master/stock/party/return tests passed (`/tmp/apex-item-name-green.log`).

Independent review correctly found e46744f's Android cache invalidation incomplete. Current core 403/404 now clears detail, PDF and statement objects as well as records/banks/readiness; the editor object and typed fields remain. A read-ownership stamp combines workspace generation and a denial epoch, so pre-denial responses cannot publish after recovery. PDF actions, reviewed party/general report exports and WhatsApp launch guards check this ownership. Editor save/quick-add require verified readiness; previews are suppressed while blocked. A draft displays a retry-company-data action. Financial dashboard/report surfaces and retained read dialogs are hidden while history is unavailable. Normal transient-only failures retain the existing authorized snapshot.

## Native verification/build readiness

- Actual AppModel.refresh method compiled in a JVM seam: four scenarios passed, checking retained draft, cleared detail/PDF/statement/preview, and stale read ownership after recovery (`/tmp/apex-android-cache-closure.log`).
- Actual PDF request methods: eight scenarios passed, including denial followed by recovery (`/tmp/apex-android-pdf-closure.log`).
- Existing actual source-selection seam passed (`/tmp/apex-source-selection-cache.log`).
- New ownership seams are wired into `.github/workflows/check.yml` after Gradle setup, using the installed Gradle compiler through `native/tests/kotlin_toolchain.py`. This runner does not download a compiler or accept licenses. Its Kotlin-distribution path was executed locally; hosted Gradle discovery still needs CI.
- Existing workflows include full Android Debug unit/lint/build, Windows Debug build, unsigned Release checks and separate UI/emulator jobs. No exact-candidate workflow was dispatched here, and no WinUI/Compose/PdfRenderer device acceptance is claimed. No unsigned build was distributed.

## Still-open findings / next work

- Parent's actual-browser revocation finding: web transaction details/download controls can remain after current access denial; generic loading/refresh copy and stale role require scoped invalidation with draft preservation. Not fixed in this batch.
- Android ToolsScreen cash-book export still reads edited controls rather than a successfully applied snapshot. This previously documented fix is not fully reconstructed; current source-level finding requires delayed/failure regressions and correction.
- Other native file workflows need the same access-ownership audit; the reviewed PDF and party/general report paths do not establish complete platform coverage.
- Viewer migration shortcuts and named member-removal confirmation are queued UX findings. Audit activity friendly labels remain queued.
- No full claim of recovering every lost change, statutory compliance, or release readiness.
