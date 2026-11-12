# Unconfirmed posting recovery boundary

The current web recovery implementation is **memory-only**. It is not durable recovery
across a reload, closed tab, browser/process failure, sign-out or a new device. Passing
retry tests does not remove that release limitation.

While the original tab is alive:

- Supported posting forms retain the original serialized operation and idempotency key
  after an uncertain response. Editing is locked; retry invokes that original operation.
- Credit and advance settlement forms stay mounted through records/access loss. Viewer
  recovery preserves unresolved status; an authorized editor can retry the original.
- Manual account/journal/reversal recovery freezes the original identifier and values.
  Exact matching reads can resolve a confirmed result. A missing, conflicting or failed
  read does not establish that the original write failed.
- Unknown period-lock saves freeze the reviewed date. A verified current lock at or
  beyond that date resolves its state. An older date does not prove the write failed.
- Pending-operation registration blocks ordinary workspace navigation/sign-out where
  required and requests a browser unload warning. Browsers may suppress unload prompts;
  a prompt is not persistence. Settings tabs retain their visited components in memory.

The UI explicitly warns against reloading, closing or signing out while a result is
unconfirmed. No financial draft payload or recovery credential is written to localStorage
or sessionStorage by this work. Server idempotency records can outlive the browser, but
that does not recover a client key which the tab has lost.

After an interruption, inspect the original company's records and reference/amount/date
before initiating a new command. Do not infer failure from absence in a bounded history
list, a failed read or an older report. If the result cannot be established, investigate
rather than issuing a replacement with a new key/reference. This document is a limitation
and operational boundary, not an automated cross-session reconciliation procedure.

Remaining acceptance work includes a designed, authenticated durable recovery mechanism,
exact integrated browser checks, native parity/device behavior, and recovery under process
termination. No production activation or deployment is authorized by these tests.
