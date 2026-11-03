# Cross-device freshness boundaries

## Observed behavior

Synthetic two-actor API checks confirm that subsequent reads reflect another actor's invoice and payment: an invoice of 100 followed by a payment of 40 yields outstanding 60 in compact records, detail, summary and party reports. Outsider and revoked membership reads are rejected. The API does not push these changes into already-open clients.

Full-app web tests reproduced skipped focus refresh while a modal was open, a dropped event inside the focus throttle, and fresh server report cards alongside older retained history after a records request failed. Native source-tied probes found the same mixed-age report/history possibility when navigating back to the dashboard. The native probes are not actual device execution.

## Web correction scope

One pending refresh intent is coalesced from focus or visibility events. It can run only when the original company/session remains current, the page is visible and editors or uncertain financial operations no longer block it. No continuous polling is introduced. Main-owned modal closure resumes the queued intent; a child-only overlay that does not rerender the workspace can still require the explicit Refresh action. Failed or deferred history refreshes retain last-good same-scope records with an explicit freshness warning; they are not presented as an empty company or a newly confirmed history snapshot.

## Separate native checkpoint

The separate native checkpoint adds a workspace-scoped last successful complete-history load time and failed-refresh status. Persistent history-snapshot labels and a guarded manual refresh action make that boundary visible. Dashboard server reports are described separately from history-derived charts and collection figures. No activation/resume refresh or background polling is added in this native batch.

## Limits

Different report and history endpoints do not provide one atomic company snapshot. A successful refresh does not guarantee that no other client changes the books immediately afterward. A continuously focused web tab receives no new focus/visibility signal merely because another client posts; native clients still need a manual refresh or an existing load trigger. These changes are not a realtime subscription, offline posting queue or process-death recovery mechanism.

No cross-company cache, new persisted credentials or financial payloads, automatic posting, OCR policy change, main-branch update or production change is included. Hosted browser smoke must not be confused with the separately blocked receipt-upload action. Native authored tests, hosted compilation and actual device execution are reported separately.

## Web checkpoint evidence

Eleven full-app synthetic freshness cases pass, including deferred modal/throttle refresh, failed history with newer reports, hidden-page behavior, pending writes, company/session replacement and dashboard remount provenance. The complete web suite passes 240 tests, lint and production build. An independent final run of all eleven focused tests passes. This is not a claim of new real-browser upload or native device coverage.

## Native checkpoint evidence

The separate native checkpoint includes four authored Android state tests and 24 authored Windows assertions. Independent source review verified complete records/banks publication before timestamps, reset and stale-response guards, retained failure status across navigation, and Windows' second manual-refresh guard before publication/navigation. The Android lifecycle proof now compiles the actual history-status helper alongside its unchanged extracted lifecycle methods. XML, Python syntax, source-boundary checks and diff checks pass. Local Gradle/SDK/.NET are unavailable, so native compilation and test execution remain hosted-CI gates; no new actual-device run is claimed.
