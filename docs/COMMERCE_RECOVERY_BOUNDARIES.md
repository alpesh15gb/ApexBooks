# Commerce recovery boundaries

## Implemented and tested locally

Money-command and order-command recovery use shared observable memory state per company/connection
within the mounted CommerceWorkspace. All form instances observe its in-flight,
uncertain, accepted and failed states. Remounting a form before the original response
cannot dispatch a second command or retain an obsolete Retry action after success.
Unknown retries retain the exact operation, payload and command ID. A definitive
validation rejection permits a new corrected request. No financial payload, token,
password or recovery object is added to browser storage.

Twenty rendered accounting-safety tests passed, including remount-before-response
success, unknown and definitive failure. The source UI explicitly warns that reload,
sign-out or leaving the workspace clears its local recovery state. Real browser,
actual integration delivery and process-death acceptance remain open.

## Why reload/sign-out replay is not implemented

The current workspace API returns at most 200 outbox entries. It has no dedicated
read-by-command-ID endpoint. A new synthetic backend test inserted an accepted command
and 205 later commands: the accepted command disappeared from the workspace window,
yet retrying its original ID/payload returned the same stored row; changing the
payload returned 409. Thus absence from the visible list is not evidence of absence
from the server. The worker may also already be delivering an accepted command.

The in-memory exact payload is lost on reload/sign-out. Generating a fresh command ID
or rebuilding from editable current fields can change the original intent. Persisting
full payloads in plain localStorage/sessionStorage would retain financial details
outside the current session; no such persistence is introduced. No automatic command
replay or new enqueue occurs on mounting the workspace or signing in.

## Prerequisites for a durable recovery feature

A future implementation needs an authorized, company/connection-scoped command
lookup with clear status semantics, a durable correlation mechanism created before
dispatch, and a policy for unresolved requests that may still be in transit. An
opaque identifier alone can support read-only confirmation of accepted commands,
but cannot recreate the exact payload when the request never arrived. Do not infer
that a single 404 permits a new financial command. Any persisted payload would need
an explicit authenticated storage design and lifecycle, not ad hoc browser secrets.

Until that feature is designed and tested, recover the original command while the
workspace remains open. After local state is lost, an authorized operator must inspect
complete server/store delivery history and reconcile the source transaction before
recording another. The latest-200 UI alone is insufficient. This document does not
claim automatic recovery across reload, sign-out or process death.

## Order-command follow-up

Invoice, shipment, credit/refund and cancellation order actions now freeze the
original operation/payload on an uncertain response and offer an exact retry.
Other order actions are disabled until that response is recovered or definitively
rejected. Each opened order dialog has separate identity, so a late response for A
cannot close a newer dialog for B. Confirmed enqueue with a failed follow-up read
is reported as accepted; only the read needs retrying. Invoice and cancellation
paths have rendered regression coverage; shipment/refund share this handler but
have not received separate integration/device acceptance.

Catalogue/history/reconciliation commands use fixed payloads and existing in-memory
command IDs for unchanged retries; this is not durable recovery. Connection setup,
verification/state and mapping endpoints are separate mutations, and this batch
does not add uncertain-outcome recovery or assert their end-to-end idempotency.
