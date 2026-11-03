# Web financial posting session isolation

## Reproduced defect

An open POS form could submit an uncertain save again after another tab replaced
its sign-in token. The request retained the original company, body and retry key,
but the shared API helper read the new token from local storage. This sent the
original financial intent under a different sign-in session. A stale form's first
save had the same issue.

This was reproduced with synthetic full-app DOM tests. No production requests or
browser actions were used.

## Bounded correction

`usePostingRequest` retains the form's originating token in memory only. Before
each operation, including exact retries, it compares that token to the current
session. A mismatch rejects the invocation before it can send a request. This
check does not depend on receiving a cross-tab storage event or a React redraw.

The guard does not infer account identity. A fresh login token, even for the same
user, cannot adopt an earlier form's command. Restoring the exact original token
allows the frozen request to be retried, subject to the server's current session,
company membership and write-permission checks. An uncertain command is not
released merely because a later retry receives HTTP 403.

The token is not newly persisted, logged, included in error messages or added to
a URL. Existing local-storage authentication behavior is unchanged.

## Verification

`tests/postingSessionIsolation.test.mjs` exercises the actual app with synthetic
fetch responses:

- An interrupted POS save cannot be retried under a different or missing token.
- A stale form cannot make its first save under a changed token.
- Missed storage events and fresh-login tokens do not bypass the comparison.
- Company switching and sign-out cannot discard an uncertain in-memory command.
- Restoring the original token preserves the exact request body and retry key.
- A server write-permission rejection leaves an uncertain command pending.
- A confirmed recovery releases the navigation/unload guard.

Existing posting-navigation and settlement-recovery tests continue to cover
company boundaries, repeated clicks, refreshed zero balances and malformed
acknowledgements. Server authorization remains authoritative; this client guard
does not grant access or bypass permission checks.

## Recovery limits

This is an in-memory protection for operations using `usePostingRequest`, not a
durable offline queue or a general replacement for application authentication.
A newly mounted form captures the then-current token. Global cross-tab UI/session
reset, including reconciliation of cached company data after an account change,
is not covered here. The guard prevents an original mounted form or pending
command from being replayed under a changed session.
Reviewed financial callbacks send their mutation when the operation is invoked.
This guard is an invocation-time check, not cancellation of requests already in
flight. Existing nonfinancial file-preparation callbacks and future callbacks
that await work before dispatch require separate dispatch-time scoping; this
review does not claim that broader coverage.

If the original session is no longer available, do not recreate the payment
blindly. Reload, sign in to the appropriate account, and review the original
company's transaction history, source document, amount and date before starting
another transaction. Recovery after sign-out, reload or process termination is
not guaranteed by this change.
