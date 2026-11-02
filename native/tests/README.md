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
