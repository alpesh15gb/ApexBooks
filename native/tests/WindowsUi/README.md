# Windows real-UI smoke (synthetic only)

This is a separate gate from `WindowsClient`/`WindowsHosted` service tests. It
launches the actual unpackaged Debug WinUI executable, uses Microsoft's managed
UI Automation patterns to enter synthetic login details, switches companies,
opens an invoice from the register and verifies its collection action. It then
creates a second 250-unit non-GST invoice **through the real form**, posts a
100-unit partial receipt through the collection dialog, and verifies one receipt,
one exact invoice allocation and a remaining balance of 150 against fresh API
responses. Finally it checks Cancel → Keep editing preserves an unsaved customer,
then Cancel → Discard produces no accounting record. Only the initial comparison
invoice is API-seeded; the invoice under financial-journey test is UI-created.

It saves app-window screenshots, an accessibility tree (no control values/passwords),
`canonical-verification.json` with synthetic financial assertions, and `result.json`.
Form entry uses UIA Value patterns resolved through control names or associated
labels; no coordinate clicks, injected keystrokes or OS security changes are used.

`.github/workflows/windows-ui.yml` publishes the app with its self-contained
runtime and an embedded `ApexApiOrigin=http://127.0.0.1:8012`, starts an isolated
SQLite API, and runs this project. The harness checks the assembly's Debug
attribute and exact embedded loopback origin **before launching**. Redirects and
non-loopback API targets are disallowed. Synthetic data uses a unique account.
It does not install UI drivers, create signing credentials or alter OS security,
login sessions, services, desktop permissions, UAC or accessibility settings.

Prerequisites are checked, not repaired: Windows and a preconfigured interactive
desktop; WinUI launch must expose a window; controls must expose standard
Value/Invoke/Selection patterns. A missing desktop, unsupported control pattern,
app launch failure or timed-out element fails the job with a precise diagnostic.
Do not mark the gate passed from compilation alone. CI must produce a successful
`result.json` plus inspectable screenshots; a failure is not equivalent to a
product defect until desktop/runtime prerequisites have been distinguished.

Official implementation references:
- [Microsoft UI Automation control patterns](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-controlpatternsoverview)
- [Managed InvokePattern](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.invokepattern)
- [Unpackaged WinUI deployment](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/unpackage-winui-app)
- [GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

GitHub's runner reference does not promise an interactive desktop for every
Windows runner. If the prerequisite gate fails, use an already-approved,
interactive Windows runner; do not change desktop/security settings in CI.
The portable client tests remain the deterministic non-UI safety gate.

Local command after publishing the Debug app and starting an isolated API:

```powershell
dotnet run --project native/tests/WindowsUi -c Release -- C:\synthetic\published http://127.0.0.1:8012 C:\synthetic\evidence
```

The legacy `native/tools/Test-WindowsHosted.ps1` now requires `-ApiOrigin` and
performs only local synthetic **service** acceptance; it is not real-UI evidence.

The initial launch/login/company-switch/detail smoke passed on a hosted Windows
runner at remote commit `185d422` (run `41522768677`). The expanded create/payment/
dirty-draft journey must pass its own subsequent CI run; compilation is not proof
that those additional UI steps passed.
