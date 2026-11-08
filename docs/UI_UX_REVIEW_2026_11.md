# UI, workflow and client-logic review — 8 November 2026

Local changes based on source `b4c1342`. This report describes the working tree, not a deployed release. All writes during verification used disposable local SQLite databases and synthetic accounts. No production credentials, books or hosted APIs were used.

## Fixes

| Area | Finding and resulting behaviour |
|---|---|
| Web dashboard | Shortcut navigation overflowed the page at tablet widths. It now scrolls within its own bounded strip. Chromium checks cover 320, 390, 768 and 1024 px. |
| Web onboarding | Compact desktop overrides removed mobile padding while icons remained absolutely positioned. Step titles and descriptions now clear their icons; dismiss stays next to the heading. |
| Web touch controls | Mobile fields inherited small desktop sizing. Document fields now use readable 16 px text, with larger input/action targets. Company loading/refresh status remains visible on mobile. |
| Web search | Selecting a transaction only filtered its register, where other filters could hide it. Selection now opens that exact transaction and refreshes its details. Party selections open their statement; item selections open the item register. References and party names are both visible in results. |
| Web keyboard navigation | Create now supports arrow keys, Home, End and Escape, with focus returned to its trigger. Empty search results cannot leave the active index negative. |
| Web filters | Collapsing filters concealed active party/sort restrictions. The mobile toggle now displays an active count and keeps Reset available. |
| Web payment flow | Saving a contextual receipt tried to reopen invoice details while its own posting lock was still active. Details now reopen after the editor unmounts, showing the refreshed balance without a misleading pending-save warning. |
| Web retry | An unknown-outcome document displayed an ordinary Save action. It now explicitly offers **Retry original save** while preserving the original request and locking its fields. |
| Web cancellation | Closing or navigating from details remained possible during cancellation. Navigation, competing actions and the reason field now lock until confirmation; a synchronous guard prevents duplicate invocation. |
| Android entry | Fields, allocations and item actions remained editable during a save or an unknown outcome. Common text/date/choice/toggle controls and mutation actions now lock; retry remains available. A quick-add operation also blocks the competing document save. |
| Android payment retry | Only the document was frozen, while the optional payment and endpoint choice were reconstructed. The whole document/payment command is now retained together. Local payment validation happens before retaining a command, so an unsent validation error cannot freeze an obsolete draft. |
| Android detail actions | The PDF/share, Receipt and Edit buttons were squeezed into one narrow row, splitting words. The footer now uses two columns on phones and three on wider windows, with single-line labels and 48 dp minimum action heights. |
| Android POS | Cart controls unlocked after a lost response even though the original sale remained pending. Quantity, price, product and payment controls now stay locked until recovery. |
| Windows totals | Changing a document left its old total available to Full amount and payment validation. The old total is invalidated immediately; Full amount and the client-side cap use a matching calculation only. The API remains authoritative. |
| Sharing across clients | Native transaction sharing missed the saved document phone when no master phone was available. All clients now prioritize the explicit party ID, then fall back to the document phone; name lookup is limited to legacy documents with no party ID. Single-document and grouped native reminders use the same helper. |
| Web reminders | Default overdue calculation used the UTC day. It now uses the same India business date as the accounting workspace, including the 18:30 UTC boundary. |

## Verification

| Check | Local result |
|---|---|
| `PYTHON="$PWD/.venv/bin/python" bash scripts/check.sh` | Passed: 243 backend tests; 125 web tests; ESLint; production Vite build; 5 live accounting HTTP journeys; complete-backup HTTP round trip; current native route contract; deployment/backup simulations. Encrypted offsite backup checks were skipped because `age` is absent. |
| Chromium production-bundle journeys | Passed: account/company creation, keyboard menu, invoice save/detail/register, partial payment, exact-document search, edit/back/discard, PDF/XLSX, ageing, recurring template, cancellation locking, four responsive widths, onboarding geometry, mobile filters, and mobile lost-response recovery. Recovery verifies exactly one invoice and one payment, with ₹100 total and ₹60 outstanding after a ₹40 receipt. |
| Android debug build/unit/lint | Passed: 52 unit tests passed, one optional HTTP smoke skipped; debug APK and instrumentation APK built; lint completed with 20 warnings and no errors. |
| Android company-load lifecycle proof | Passed: the production company-load operation survives disposal of the restore dialog when run in the session-owned task. |
| Android native emulator journeys | Passed: all 4 instrumentation tests on Android 10 / API 29. Real native controls verified sign-in, special-character passwords, company switching, invoice entry and collection, keep/discard, reorder and price/terms review, retained receipt upload/archive through the system picker, encrypted backup/restore and financial/evidence round trips. Device HTTP/PDF/image tests also passed. |
| Windows portable client | Passed: 137 checks covering HTTP/session isolation, retries, capability compatibility, company loading, backup transfer and the new sharing-phone regressions. |
| Windows C# syntax | All 44 Windows source files parsed successfully using the installed .NET SDK's Roslyn compiler. This is not WinUI compilation or runtime acceptance. |
| Full Windows application | Not runnable on this Linux host. The normal build stops at NETSDK1100. Run the existing Windows build and `windows-ui.yml` gates on Windows before packaging a release. |
| Source hygiene | `git diff --check` passed. |

The browser harness initially assumed saved documents returned directly to the register; it now explicitly handles the existing automatic detail screen. Native UI automation also used the older dashboard wording **Low stock & reorder review** and tried to use background navigation while the new post-save detail was open. It now targets the visible **Low stock review** action and closes the detail explicitly, preserving the reorder, financial, native picker and backup assertions.

## Reproduce

Use Python 3.12, Node, the pinned backend requirements and `npm ci --prefix frontend`. The initial system Python 3.14 cannot install the pinned psycopg binary; verification used an isolated Python 3.12 environment without changing dependency versions.

```bash
PYTHON="$PWD/.venv/bin/python" bash scripts/check.sh
.venv/bin/python tests/e2e/run_local.py --browser --artifacts .native-build/browser-evidence

dotnet run --project native/tests/PortableClient/PortableClient.csproj

cd native/android
bash gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest --no-daemon --max-workers=2
```

For real native UI journeys, follow `native/tests/README.md`: use a dedicated emulator and a fresh local API on port 8012, then run `native/tools/run_android_device_checks.sh`. The local emulator used Android 10 / API 29 with the debug app, no production session and no changes to virtualization-device permissions. Browser evidence is in `.native-build/browser-evidence`; Android reports and synthetic screen evidence are in the ignored `native/android/app/build` directory.

## Remaining release gates

Windows WinUI compilation, interactive desktop acceptance and native printing/sharing still require Windows. Android emulator checks do not establish physical-device behaviour, camera/barcode services, hardware printing, release-signing/update acceptance, or every Android OS version. Firefox/Safari and PostgreSQL concurrency were not exercised in this review. Existing tax/accounting scope and deployment gates in `RELEASE_CHECKLIST.md` still apply. These changes are local source changes; no deployment or signed release was published.
