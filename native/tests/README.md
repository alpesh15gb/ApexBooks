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

The local Android device journey also creates an invoice through the native
party/item/review/save controls, verifies canonical amount/outstanding via the
isolated API, and checks Keep editing versus Discard causes no accidental post.
Its feature review steps cover reorder-to-draft, explicit price-basis Apply,
and payment-terms Apply without saving those exploratory drafts. This expands
the compiled instrumentation suite; completion requires actual CI device results.

## Compatibility and business-date regressions

Android `ApiCapabilitiesTest` covers an older API returning 404, unavailable
capability metadata, unknown contract versions, and omission of untouched
unsupported master defaults. Transient network failures expose an explicit
background Retry feature check rather than falsely requiring a server upgrade;
normal record refresh does not repeatedly probe capabilities. Unsupported user edits are rejected explicitly,
not reported as saved; optional controls explain the server upgrade requirement.
Book labels are workspace labels only and never replace the legal company name.
Shared date defaults use India business midnight (18:30 UTC), independent of the
device timezone. `ToolDraftStoreTest` verifies activity recreation retains the
original financial tool payload and retry key, and unresolved drafts cannot be
discarded. This holder is session-only, not process-death persistence.

The Windows UI harness targets the visible item AutoSuggestBox with genuine
keyboard input, rather than its unattached internal description model. On a form
or failure it can emit one bounded synthetic app-only JPEG in CI logs for visual
review when artifact download tooling is unavailable; full PNG/AX evidence stays
in the isolated test artifact. No production records or credentials are captured.
