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
checks remain necessary. Android transfer source has a similar successful-response
ownership question and still needs an independent compiled reproduction before
claiming parity. Full WinUI/Compose builds, device rendering/printing/sharing and
final exact-commit CI remain open. The user owns deployment; none was performed.
