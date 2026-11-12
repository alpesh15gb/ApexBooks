# Web access-loss recovery and Android pending reads

Local follow-up to 28ded2e. No production access, publication or deployment.

## Web behavior

Company-scoped fetches now retain an access epoch through headers, body methods and streamed reads. A current 403/404 triggers a separate membership read: an authorized viewer's owner-only 403 or a missing document's 404 does not by itself revoke the workspace. Missing or unverifiable membership locks that company's workspace with an explicit access-loss/unavailable message. A late response for another company cannot lock the current one. Membership-confirmed roles refresh cached role metadata.

The App hides/inerts the old workspace and clears open transaction/party read views while keeping draft components mounted. Recovery checks membership, then reloads records before unlocking. A draft restored under viewer access remains visible but cannot be saved; it can still be cancelled. No draft is automatically discarded or submitted. Body/stream responses from before denial remain invalid after recovery. Receipt and complete-backup downloads also recheck company ownership immediately before their final save side effect.

This is reaction to observed access denial, not an instantaneous push notification of remote revocation. The server remains authoritative for every write. Already downloaded files cannot be revoked. A failed membership check is described as unavailable, not proof that the owner removed access. If access is not restored, drafts remain in memory in the tab; reloading the browser can still lose unsaved work.

## Android correction and pending-read guards

The prior reported cash-book unapplied-filter bug was traced to **unreachable BasicTool code**. ToolsScreen actually routes cashbook to CashBookTool, which already retained its applied filter snapshot. That earlier source-only finding is withdrawn for the active route. The dead unsafe branch is removed to avoid future reuse/confusion.

The active tool now labels the displayed bank as well as dates, verifies cancellation/access ownership after report fetch, and rechecks ownership/tool presence before saving exported bytes. Four tests compile its actual load/export bodies: edited/failed filters keep the displayed export scope; a cancelled load cannot publish even if transport ignores cancellation; denial/recovery and close suppress pending exports.

EntryEditor source selection captures read ownership and rejects both stale success and stale failure after denial/recovery. Actual-method compiled scenarios cover these plus existing dirty-draft/failure/selection cases. AppModel edit/convert similarly gate dispatch and publication; eight actual-method scenarios passed for success, denial, recovery and stale errors. Unsaved draft objects remain unchanged in rejected cases.

## Executed evidence / limits

- Frontend final full suite: 209 tests passed, lint and production build/bundle budgets passed. The eight-test targeted access suite also passed. Logs: `/tmp/apex-web-access-complete.log`, `/tmp/apex-web-access-final-targeted.log`, `/tmp/apex-web-access-final-build.log`.
- Rendered App regressions exercise a revoked master save, editor/viewer recovery, retained input identity, inert restoration and an open viewer transaction cleared on revoked refresh. These are JSDOM, not actual-browser acceptance.
- Android cash-book body seam: four scenarios (`/tmp/apex-cashbook-proof.log`); edit/convert: eight (`/tmp/apex-editor-access.log`); source selection: extended actual-method matrix (`/tmp/apex-source-access-final.log`).
- Cash-book, editor and source-selection seams are added to existing CI using the installed compiler runner. Exact-SHA full Android/Windows CI and physical-device/Compose/PdfRenderer acceptance remain open. Hosted compiler discovery is not claimed executed here.
- No backend accounting behavior changed in this batch. Existing live/local browser evidence from 9159cbf is not final-revision acceptance.

Remaining UX queue includes viewer migration shortcuts, named member-removal confirmation and friendly audit-event labels. Other native file workflows still require the same access-ownership audit; this batch does not certify every download path or all lost reconstruction work.

## Stock draft role recovery follow-up (2026-11-12)

Independent review found that retained Opening stock and Stock adjustment forms
remained postable after access recovery as a viewer. Both forms now accept a
read-only role state, disable posting and editable fields, and refuse direct
submit events. The App save handlers independently reject missing writer roles
or an access-loss state. Draft values remain mounted; Cancel remains available
when no posting outcome is pending. Server authorization is unchanged.

Four rendered-App regressions exercise both forms through current access denial
and recovery as viewer/editor: the same draft input survives, viewers make no
POST even through a synthetic submit event, and editors post once. These use a
synthetic fetch transport; final browser acceptance remains separate.

## Native harness toolchain verification (2026-11-12)

Downloaded Gradle 8.14.3 from the official downloads.gradle.org distribution
endpoint to a temporary directory and verified its official SHA-256:
`bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531`.
Using Java 21 and that distribution's bundled Kotlin compiler, all six compiled
checks completed successfully: AndroidPdfLoading, AndroidCoreRefresh,
AndroidCashBook, AndroidEditorAccess, AndroidSourceSelection and AndroidLifecycle.
The lifecycle check intentionally demonstrates the former failure before testing
the corrected production methods; its REPRODUCED line is expected.

Command for each: `JAVA=/usr/lib/jvm/java-21-openjdk-amd64/bin/java python
native/tests/<name>/check.py --gradle-home
/tmp/apex-gradle-readiness/gradle-8.14.3`. Logs are in
`/tmp/apex-gradle-readiness/<name>.log`. These compile extracted production methods
with harness types, not the full Android application. No Android SDK licenses or
security-setting changes were made. Full final-commit Windows/Android CI builds,
Compose/WinUI device interactions, rendering and printing remain open. Nothing
was uploaded, merged or deployed in this follow-up.
