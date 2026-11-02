# Native regression checks

- Portable HTTP/session and uncertain-save tests (test-only in-memory credential vault):
  `dotnet run --project native/tests/PortableClient/PortableClient.csproj`
- Real Windows credential-vault transport checks:
  `dotnet run --project native/tests/WindowsClient/WindowsClient.csproj`
- Android compile, unit tests, lint and debug APK:
  `cd native/android && bash gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug`

## Android device acceptance: local synthetic data only

Run `python migrate.py` from `backend` with `DATABASE_URL` pointing at a fresh disposable local database, then serve that API on port 8012 and use a dedicated emulator. The debug default `http://10.0.2.2:8012` points back to the emulator host.

`bash gradlew :app:connectedDebugAndroidTest`

On Windows, `native/tools/Test-AndroidHosted.ps1` retains its old filename but now runs **local debug acceptance only**. It does not read release signing credentials. Tests fail closed unless the build is debug and its API address is a local HTTP host. They register unique synthetic accounts; no personal credentials are needed. Never point these tests at hosted data.

`LocalUiAcceptanceTest` exercises actual native sign-in, company switching, invoice details and a prefilled receipt save; it verifies the resulting invoice balance and exactly one posted payment. The legacy-named `NativeHostedAcceptanceTest` exercises device HTTP posting, GST/stock controls, PDF rendering, and image processing against that same isolated API. `LoginTransportAcceptanceTest` checks invalid credentials and password encoding. These are not production acceptance or proof of every manual print/share flow.

## Company-load regression checks

`CompanyLoadTest` (Android JVM unit tests) and `WindowsClient/Program.cs`
(portable or Windows runner) exercise a synthetic 1,250-record company with
20 ms injected latency per records request. The previous 100-row loop needs
13 requests; current 500-row compact paging needs 3 and asserts all 1,250
unique IDs are retained. Local runs on 2026-11-02 measured 386 → 91 ms for
Android loopback HTTP and 273 → 65 ms for Windows injected transport. These
are client regression measurements, **not production or device UI timings**;
server query cost, payload size, hardware and real network latency differ.

JSON parsing/list assembly runs off the UI context. Android shows authoritative
report totals while history loads, does not repeat its three report requests
merely because initial history finished, and hides history-derived charts and
billing until history is complete. Windows retains a complete-history loading
state before its full dashboard. Neither implementation uses a cross-company
record cache or presents partial-page balances as complete financial totals.

## Planning workflows to verify on a device

- Edit a saved party: optional payment terms accept 0–3650 whole days.
  Invoice/bill **Check party payment terms** fetches the API suggestion;
  only **Use suggested due date** / **Replace due date** changes the draft.
- Link a saved party and item: **Check this party’s item prices** shows up to
  five posted exact-ID matches. **Apply suggested price & tax basis** changes
  only rate and inclusive/exclusive basis, with the current GST/discounts left
  visible for review. Changing party/item invalidates the displayed suggestion.
- Edit tracked goods: optional nonnegative threshold (three decimal places)
  enables **Low stock & reorder review**. Search and inspect authoritative
  dated stock, then prepare a purchase-order draft. Supplier/quantity/rate
  review and explicit save remain required; opening the report or draft never
  posts stock or sends an order.

`PlanningToolsTest` covers Android optional-field boundaries. These are new
UI flows: local build/unit checks do not replace device acceptance evidence.
