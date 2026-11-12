# Native response ownership and CI availability (2026-11-12)

## Connected CI check

The GitHub connector read PR59 successfully: it remains a draft at
`fc415d654e0f1a4afd2c335a2b1202586ec1c695`, not the later local branch.
Its PR-triggered workflow lookup returned no runs for local
`bcc8d89e40619473317da3c50deeb26b8aca6910`. This endpoint is limited to the first
page of PR-triggered runs; it is not a claim about every possible CI trigger.
Available connector tools inspect or rerun existing jobs, but do not dispatch a
workflow for unpublished local content. No rerun, branch upload or remote mutation
was attempted. Earlier green native CI cannot validate this local candidate.

Full Android build prerequisites remain unavailable locally: the offline probe
stopped at Android Gradle plugin resolution before source compilation, and no
Android SDK is installed. Full Windows builds require Windows/WinUI tooling.
Portable compilation below is intentionally distinguished from those gates.

## Reproduced Windows response ownership defect

A synthetic in-memory HTTP transport delayed a successful JSON response until
after sign-out. Actual ApexApi.Send returned the old successful data. The red
regression failed with `Stale successful json response escaped after logout` in
`/tmp/apex-native-session-red.log`. No real HTTP endpoint or user data was used.

Send, Download, SendBytes and DownloadBounded now capture the token and session
generation atomically. They verify ownership after reading/parsing successful
responses and before returning; bounded streams also verify during consumption.
A replacement session never receives the old response or gets logged out by it.
The failure uses status 0 so an already-dispatched financial write remains
uncertain and retains its original retry payload. Login retains its independent
attempt-sequence guard; existing delayed login and old/current 401 tests remain
part of the compiled suite.

ResponseSessionRegression covers all four paths, delaying either headers or body,
with unchanged session, sign-out, replacement, and replacement using the same token
string. That last case checks generation ownership rather than token comparison
alone. Test identities are .invalid and all HTTP/stream work is in memory.

## Executed verification

The complete portable client suite passed with the 32 new delayed-header/body
ownership cases and existing 401/login cancellation, CSV, source selection,
core-refresh, retry and backup transfer tests. Command:
`dotnet run --project native/tests/PortableClient/PortableClient.csproj -c Debug`
using the temporary .NET 10 SDK. Final log:
`/tmp/apex-native-session-final.log`. Real Windows vault/WinUI testing remains open;
the portable harness supplies an in-memory vault. No credentials are logged.

## Limits and follow-up

This is transport-boundary protection, not cancellation of a server write and not
proof of every native final file-save/share side effect. Higher-level workspace
checks remain necessary. The Android ownership question identified here is addressed by the follow-up
below; full application and platform behavior still require acceptance. Full WinUI/Compose builds, device rendering/printing/sharing and
final exact-commit CI remain open. The user owns deployment; none was performed.

## Android parity and same-token invalidation follow-up

The Android actual-method seam reproduced a successful request returning private
synthetic data after sign-out (`/tmp/apex-android-response-red.log`). The methods
now capture token/generation under the session lock, check ownership around byte
transfer and dispatcher-based JSON parsing, and leave interrupted write outcomes
uncertain (status 0). Login retains its separate attempt-sequence guard.

Independent Windows review additionally found that the old Logout finally and
401 Failure handlers compared only token strings. A local compiled regression
confirmed the old logout cleared a same-token replacement session. Both Windows
paths now require the captured generation as well. Android logout and 401
invalidation use the same token/generation policy. Current-session expiry and
credential-challenge behavior are retained.

Verification: the complete Windows portable suite passes its existing cases,
32 successful-response cases and two new same-token logout/401 regressions; log
`/tmp/apex-native-logout-green.log`. Android compiles the actual session/request/
transfer method block using verified Gradle 8.14.3 and exercises 40 delayed
header/body/JSON-parse cases plus six current/stale logout, 401 and credential
challenge cases; log `/tmp/apex-android-response-final.log`. The harness supplies
minimal synthetic JSON/vault/BuildConfig fixtures and an in-memory HTTPS URL
handler; it never opens a real network connection. It is not full application,
real Android JSON/Keystore, Compose or device acceptance. The new check is wired
into check.yml for later authorized CI; no workflow was dispatched.

## Android final Save picker boundary

A compiled NativeFiles method probe reproduced a stale picker writing byte data
following a simulated workspace change. Red log: `/tmp/apex-save-ownership-red.log`.
The API response checks alone cannot protect the later OS picker callback.

NativeFiles now captures a save-ownership verifier when opening the picker.
AppModel supplies the actual API session guard plus company/read-access stamp.
The callback verifies before opening the destination and before file-copy chunks;
account changes, company switches, access denial and recovered access invalidate
the old operation. Opening a second export cannot replace the pending picker's
bytes or callback. Cancellation and picker unavailability/failure clear the pending
operation and report false to a file-export completion callback. No original
staging file is deleted by this guard.

The compiled actual-method/wiring harness passes 14 scenarios: bytes/files with
current/stale ownership, six AppModel scope states, duplicate picker launch, and
cancel/unavailable/throwing picker. Log `/tmp/apex-save-ownership-final.log`.
The 46 transport cases also pass again in
`/tmp/apex-android-response-save-followup.log`. The harness is added to check.yml;
no CI dispatch or publication occurred.

Limits: the resolver/picker and JSON/vault remain synthetic. A real OS picker may
create an empty destination before returning it; the app will not open/write that
file after a failed guard. If access changes during an already-started streaming
write, checks stop subsequent chunks but cannot undo bytes already written. We do
not delete user-selected files as a rollback. Android print/external share and
Windows Save/SaveStream picker boundaries remain separate acceptance/review
items. Full builds and physical-device acceptance are still open.

## Windows picker and Android pre-picker follow-up

Windows actual Save/SaveStream methods reproduced a stale byte export after a
delayed picker returned (`/tmp/apex-windows-picker-red.log`). Both now require a
captured verifier installed by MainPage, checking session generation, company,
workspace generation and an access-denial epoch. Byte saves check before writing;
stream saves also check after asynchronous destination opening and between chunks.
Access loss followed by recovery does not make the old picker valid again.
The previous catch-and-delete cleanup is removed: a failed stream export must not
automatically delete a selected pre-existing user file. A later failure can leave
a partial file; no rollback or atomic replacement claim is made.

Fourteen compiled actual-method/wiring scenarios pass: current/stale byte/stream
saves, seven scope states, byte/stream cancellation, and access change during
destination opening with original synthetic bytes preserved. Log:
`/tmp/apex-windows-picker-final.log`. Picker/storage/WinRT types are test doubles;
full Windows build, actual picker/providers and filesystem acceptance remain open.

Independent e1a818e review correctly identified an earlier Android boundary:
legacy backup/data-export fetched or encrypted before capturing picker ownership.
ToolsScreen now delegates those paths to a scoped operation capturing the original
session/company/read stamp and tool before fetch. It rechecks after fetch and
encryption and immediately before Save. Stale successes/errors do not open a
picker or close/update the replacement workspace; current errors remain visible.
Twenty-four compiled cases passed for delayed fetch/encryption, company/session
changes, denial/recovery, closed tool, current and stale errors; log
`/tmp/apex-legacy-export-final.log`. Encryption is deliberately a delayed fixture
in this flow test, not a fresh cryptographic test.

Both harnesses are wired into existing check.yml. No CI dispatch, publication or
production action occurred. Remaining review: Windows callers that fetch/encrypt
before invoking Save need their original context checked before entering the
picker; a guard captured only at Save cannot establish the origin of old bytes.
Full native builds, real picker/runtime and final sharing/printing acceptance
remain open.

## Windows pre-picker caller correction

Independent bc11103 review confirmed that the picker guard alone did not cover
legacy backup/data export and cash-book downloads, or complete-backup asynchronous
encryption. These four callers now capture original MainPage ownership when the
flow opens, retain it through download/encryption and pass that same verifier to
Save/SaveStream. `ScopedFileExport` suppresses stale successes/failures, preserves
current errors, and distinguishes stale work (null) from picker cancellation
(false). Backup progress updates also require original ownership. No operation
is retried or submitted automatically.

Evidence:

- Full portable Windows client suite passed with 11 added scoped export cases
  (delayed fetch/transform, current/stale errors, cancellation and stale entry).
  `/tmp/apex-windows-export-context.log`.
- Actual callback bodies from Settings, Accounting and CompleteBackups compiled
  in a synthetic control/transport/crypto harness: 24 cases passed, including
  company-context loss during complete and legacy backup encryption with no file
  side effect. `/tmp/apex-windows-export-callbacks.log`.
- Fourteen actual picker/wiring cases passed again with the optional original
  verifier parameter. `/tmp/apex-windows-picker-export-followup.log`.

The callback harness does not compile the surrounding WinUI pages or use real
cryptography. Exact full builds and device/provider acceptance remain open. Other
report/PDF/recovery-code/attachment callers have separate existing generation
checks, but their retained read-access epoch/final external-side-effect coverage
still needs review; these four corrected flows are not a blanket closure of all
native export paths. No production action, CI dispatch or publication occurred.
