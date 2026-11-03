# In-flight financial response session boundary

## Reproduced failures

Synthetic deferred-fetch tests demonstrated that the pre-invocation session guard
alone did not protect responses already in flight:

- A POS success from the original session displayed a receipt, cleared its cart
  and refreshed company records using a replacement token.
- A partial invoice receipt for 40 against an outstanding 40 closed its editor
  and refreshed records using the replacement token.
- A records refresh started while a POS save was in flight could return HTTP 401
  after a cross-tab token replacement and remove that replacement token.

Normal company switching remained blocked throughout these pending saves. The
failures required only a normal cross-tab token change and delayed responses.

## Bounded changes

The main app API helper captures the session used when dispatching its request.
It checks that session after fetch completes, after JSON success or error-body
parsing, and on fetch/parse failure before returning data or an error status to a
caller. This is deliberately before `saveRecord` can refresh or close its editor,
and before `loadRecords` can handle an old HTTP 401 as a current sign-out.

An ignored response raises a session-change error with status 0. It does not
expose the old response's HTTP 401/403 to handlers for the replacement session.
It also does not claim that the original financial request failed to commit.

`usePostingRequest` additionally wraps the stored operation with completion and
error-time session checks. This protects reviewed direct-fetch callers such as
cash/bank transfer, whose UI updates and refresh callbacks happen after the
posting helper resolves. The existing pre-invocation guard remains in place.
An ignored completion/error retains the original operation and its retry key.

## Verification

`tests/inflightPostingSession.test.mjs` uses synthetic full-app DOM tests with
deferred fetch or deferred JSON parsing. Nine cases cover POS, partial receipt,
records-refresh 401 and direct cash/bank transfer success/error responses.
Each verifies that the replacement session cannot replay the old command, the
original token can recover it, a server permission rejection retains uncertainty,
and recovery uses the original company, body, retry key and authorization.

No production records, live services, browser actions or attachments are involved.

## Limits and recovery

The change does not cancel an already dispatched request or undo a server commit.
It suppresses stale client-side handling and preserves the in-memory command for
recovery. It is not a durable queue, a persistent exactly-once guarantee, or global
cross-tab authentication/UI reconciliation. Newly mounted forms and other API
helpers are not automatically covered by the main app API boundary.

For raw Response consumers, the main API check runs before returning the Response;
body consumption performed later by a caller is outside that check. The shared
posting wrapper checks completion of its whole callback, but cannot protect side
effects the callback performs before it returns. Callbacks that await file
preparation also need their own session validation at eventual dispatch. Receipt
uploads and other attachment flows were neither exercised nor changed here.

If the original session cannot be restored, reload and inspect the original
company's transaction history before creating another payment. Recovery after
reload, sign-out or process termination is not guaranteed.
