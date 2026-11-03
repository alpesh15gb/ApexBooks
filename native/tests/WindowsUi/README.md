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
labels; no coordinate clicks or OS security changes are used. The editable item selector uses genuine keyboard text entry and Tab to commit its visible value.

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

The next retained-evidence gate additionally seeds a synthetic purchase bill,
opens its actual detail → Retained receipts, selects a generated PDF through the
real Windows **Open** picker, uploads and archives via actual controls, verifies
canonical bytes/hash/state, and enters Settings → complete-backup dialog. It preserves all mandatory invoice250/collection100/balance150
and dirty-draft assertions. Picker automation targets the English hosted runner's
owned `Open` descendant window and `File name` field; missing/inaccessible picker fails with the
usual diagnostics rather than substituting a hidden API upload. This extension is
compiled locally but **requires its own Windows CI execution** before success can
be claimed. No OS permission/security changes are performed.

CI run `41543179994` reached the genuine Open picker, visible both in the app-window screenshot and its descendant UIA tree, but the old desktop-child selector timed out. The selector now stays scoped to the launched app’s descendants; it still requires the real File name edit and Open button and never substitutes an API upload. Subsequent run `41550655675` passed the receipt picker, retained-byte/archive checks and backup entry. The extended encrypted save/restore journey below still requires its own runtime result.


## Encrypted complete-backup round trip

The next gate extends the same mandatory financial and receipt journey:
- Keep recommended local encryption selected, enter a synthetic-only passphrase,
  export through the actual **Save As** dialog to a fresh `.apexbackup` path,
  and assert the saved file is the encrypted v1 envelope.
- Open that file using the actual native **Open** dialog, name a new company,
  enter its passphrase, and explicitly validate/preview before committing.
  Assert preview alone has created no company.
- Confirm restore through the real UI, require exactly one distinct new company,
  and navigate to its dashboard. Compare fresh canonical summary and financial
  accounts with their pre-export source responses, including the partial invoice
  settlement. Download the restored archived receipt through the read-only API
  and compare its bytes and SHA256 with the original synthetic PDF.
- Re-query the original company's records, reports and archived receipt metadata
  to prove the source was not overwritten. Save `backup-roundtrip-verification.json`
  and screenshots of the saved export, reviewed preview and restored dashboard.

These extra steps compile locally but require a new interactive Windows CI run;
compilation does not establish picker or restore execution. Every picker remains
scoped to the app-owned dialog. There is no service export/restore substitute,
plaintext fallback, skipped assertion, or OS permission change. The retained file
and passphrase are generated synthetic fixtures only, never user backup data.


Run `41559696848` passed the mandatory rapid typing/control-identity check and
all existing financial/receipt assertions, then exposed a shell **Save As** COM
warning: “An outgoing call cannot be made since the application is dispatching
an input-synchronous call.” The test now verifies the exact destination and
keyboard focus on the real Save button, then activates it once with Space instead
of synchronous UIA Invoke. It does not dismiss the warning, repeat an uncertain
save, alter the app, or bypass the picker. This repair still requires CI execution.


Run `41561397371` confirmed the visible-action guard must navigate the long
Settings page rather than invoke an offscreen control. The harness now uses the
actual Settings search with the exact Download/Restore action names before
waiting for their visible, enabled buttons. It does not remove the visibility
check or invoke hidden controls. All prior rapid typing and financial/receipt
checks passed in that run; the Save repair and backup round trip still await CI.


Run `41564385744` closed the Save dialog and completed export staging cleanup,
but no file appeared at the required destination. The filename had been set via
ValuePattern only. The test now enters that path with genuine focus-confirmed
keyboard input, commits the edit with Tab, verifies the exact text again after
focusing Save, and captures the picker before one activation. The expected-path
file and encrypted-envelope checks remain mandatory; no alternate file is accepted.
The destination-binding explanation is an inference pending the next Windows run.


Picker discovery first searches the app UIA subtree. For desktop-level shell
windows, it verifies the app HWND still belongs to the launched process and
requires the candidate's native `GW_OWNER` chain to reach that HWND. Matching
process IDs or window titles alone never authorize a candidate. Traversal rejects
zero handles, cycles and chains beyond 64 hops. The same finder is used for
receipt upload, encrypted Save and restore Open; all real file and hash assertions
remain mandatory. `WindowOwnership.cs` is linked into portable/client tests with
direct, nested, unrelated, cyclic and depth-boundary regressions. A new hosted run
is required to validate desktop-level picker execution.


The native inline-master candidate adds real-UI steps to the financial journey:
cancel an inline customer without losing the invoice reference, create/select a
customer, then create a zero-rate service after entering the existing250 line.
The appended review line must preserve the original quantity/rate; the saved
invoice must contain both returned master IDs and exactly two lines. The existing
250 invoice,100 collection,150 balance, dirty-discard, receipt and encrypted-backup
assertions remain unchanged. These new steps are authored but not yet compiled or
executed in the current environment, which lacks .NET. No runtime pass is claimed.


PR5 run `41592390939` passed inline customer creation/cancellation and preserved
the invoice reference, then showed the item-create action below the dialog's
viewport. Focus alone did not reveal it. The test now uses ScrollItem when
available or the button's nearest vertical ScrollPattern ancestor (bounded40
small steps), then still requires a visible enabled button before invocation.
It never scrolls the desktop or invokes the hidden action. Runtime recheck pending.

### Picker discovery diagnostics

On a failed synthetic run, `picker-diagnostics.json` records the launched app's
HWND/PID, matching top-level `Open`/`Save As` UIA and native window metadata, and
bounded native owner chains. It captures at most 16 candidates per source and
32 owner nodes per candidate; it reads no filename fields or document contents.
Native enumeration is diagnostic only. Picker selection still requires the
existing app subtree or verified native ownership chain, with visible/enabled
controls. No extra picker activation, upload or action retry is performed.

This diagnostic addition passed local diff/source checks; compilation and runtime
capture require the Windows CI runner because the local .NET SDK is unavailable.

### PR32 owned reveal follow-up

Run 41673718317 (artifact 13250416085) reached the inline-item action after customer creation and exact/rapid item typing. The failure screenshot and accessibility tree show `+ Create item here` present below the visible form area; no item-create action or POST was issued. The earlier helper scrolled once, then waited passively. The exact cause of the later visibility state is not established by those older diagnostics.

The test now reevaluates only the identified app control and its owned scroll container during a bounded readiness wait, retaining visible/enabled/positive-size requirements before the existing single action. Failure output includes bounded geometry and scroll diagnostics. All accounting and backup assertions remain unchanged. Local .NET is unavailable; compilation and real hosted UI execution are pending for this test-only correction.


### Live picker anchor regression

The synthetic PR41 failure artifact showed a visible shell Open dialog owned by
its launched process's main HWND, while the cached WinUI content UIA HWND differed
and desktop UIA children omitted the dialog. Picker discovery now refreshes the
launched Process.MainWindowHandle and verifies its native PID and visibility.
It retains UIA subtree/desktop discovery and adds bounded native enumeration
(maximum 2048 windows), but only materializes a candidate with FromHandle after
its visible/enabled native owner chain reaches that verified live anchor. The UIA
handle, native PID, title, visibility, enabled state and positive bounds must match.
A title or same process ID alone never qualifies a picker. The captured anchor
and ownership are checked again before file input and the single final action;
a changed anchor aborts rather than retrying or retargeting. Existing financial,
file, hash and backup assertions are unchanged.

Seven additional pure anchor-policy assertions run in both portable and Windows
client suites. Local static checks are not compilation or native picker proof;
the corrected real picker path requires a hosted Windows UI run.
