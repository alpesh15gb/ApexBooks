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
