# Company JSON export response scope

Synthetic deferred-response review on PR45 reproduced an old-company JSON export
being dispatched after company, authentication token, owner role or mounted view
changed. Both response-header and blob-read delays reproduced it; late errors
also appeared in the replacement company. The probe mocked fetch, object URLs
and anchor clicks. No browser, network, real user file or receipt upload was used.

CompanyDataExport now captures the original company, owner role, token and one
active operation. It checks scope after each awaited response/body/error parse
and immediately before file dispatch. Company/role replacement, unmount and
cross-tab token/clear events invalidate the operation and attempt cancellation.
Returning to the original token does not revive an invalidated request; a new
explicit download is required. No state, key or token is persisted by this change.

Stale errors are suppressed. Old completions cannot clear a newer operation's
busy state. Object URLs are scheduled for revocation even when anchor dispatch
throws or the operation becomes invalid after URL creation. Abort is only a
resource-saving measure; guards remain necessary when a transport ignores it.
A dispatch already completed before a switch cannot be revoked retroactively.

The owner-only export's successful behavior and complete-backup-required guidance
remain unchanged. This does not alter receipt upload/archive, receipt downloads,
backup import/restore or other export views. Separate receipt streaming/token and
refresh-state findings remain outside this checkpoint. Synthetic tests do not
replace actual browser acceptance or the original pending upload approval.

Verification: 30 targeted synthetic tests pass; the same suite against original
source 890d9dd produces 27 failures and three legitimate-path passes. The full
270-test web suite, lint and production build pass. These checks cover observed
cross-tab storage events, not an unobserved same-document token A→B→A transition.
No real browser download is claimed.
