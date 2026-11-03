# Financial save recovery after process death: design only

Assessment baseline: consolidated CI source `eb2ad6a249b0b38dccb946d610f668cd57ef07e2`
(tree `4009f5fcbbb5a43bf3227cb456160b75902b599e`). No application, schema,
endpoint, storage or replay behavior is changed by this document.

## Decision

Do not implement crash replay from the current contracts. An interrupted save may
have committed. The disappearance of an in-memory command, a missing lookup,
expired authentication or a restored database cannot establish that it did not.
Never rotate its key or submit a replacement automatically. Current recovery is
session-memory recovery, not process-death or offline posting support.

The smallest defensible future scope is **read-only reconciliation**, initially
for new commands with explicit server receipt support. It must not persist
financial payloads or authentication secrets on clients. Recovery of unsaved form
content is a different problem and is not promised here.

## Existing evidence and gaps

- `frontend/src/postingRequest.js` keeps the pending operation closure in memory;
  `postingSession.js` binds it to the current session token. A synthetic lost
  response leaves the original closure pending, while constructing fresh state
  yields no pending operation. The test performs one synthetic send only.
- `backend/main.py` defines record bindings unique by company/key, storing a
  request hash and record ID. They lack actor, operation, creation time and expiry
  metadata. Record replay returns the current record, which may have been edited
  since the original successful request.
- Journal bindings are company/operation/key scoped and retain a response
  snapshot, but also lack actor/time metadata. Existing route-specific hash
  builders differ; financial amendments even distinguish omitted expense amount.
  A generic hash algorithm or newly defaulted date would not be equivalent.
- There is no generic authenticated command-status endpoint. Authorization is
  checked before replay. Portable company backups omit operational bindings;
  restoring data does not restore proof that an old command key is safe to reuse.
- Native command stores are in memory. Existing session credential facilities
  are not a proven durable, actor-scoped financial intent journal. No storage
  implementation or crash-durability test is introduced here. Android
  `data/SessionVault.kt` uses Keystore-backed encryption but asynchronous
  SharedPreferences writes and silent clearing after decryption failure must not
  be copied into a recovery journal. Windows `Services/ApexApi.cs` uses
  PasswordVault for credentials, not a general financial journal. Neither client
  currently exposes the stable authenticated actor ID needed by this design.

Legacy matching bindings can provide positive evidence of a committed operation
under appropriately authorized inspection. They cannot establish historical
actor attribution. Similar names, totals or dates are not unique command proof.

## Prerequisites for a future read-only receipt capability

1. Stable server-authenticated actor ID, original company ID and server/dataset
   namespace. Email, a cached company name or a bearer-token string is not a
   durable identity. A renewed login by the same actor is distinct from permission
   to switch to another actor's command.
2. Versioned operation/target identity and a cryptographically random command ID,
   bound transactionally to the exact request interpretation. Reuse existing
   route-specific normalization where applicable; keep original explicit dates.
   New records require actor attribution at creation, not an inferred backfill.
3. A minimal durable server receipt committed atomically with the business write,
   plus an authenticated read-only lookup/list scoped to that actor and currently
   authorized company. Opaque IDs must not act as bearer authorization. Return
   bounded metadata and a resource reference, clearly distinguishing current
   record state from an immutable original response.
4. Discovery after reauthentication without depending on a lost client closure.
   A server-owned actor receipt list is preferable for the web to a financial
   payload journal. A persisted native opaque receipt hint would require a
   separately reviewed secure/durable storage design and is not implemented.
   Without a surviving command ID/fingerprint, a receipt list cannot identify
   which save was interrupted, especially across multiple devices. Show candidates
   for review; never automatically select the latest similar receipt.
5. Explicit server/dataset incarnation and recovery behavior. A portable restore,
   account removal, lost encryption key, database recovery or expired receipt
   must not silently convert uncertainty into permission to post again.
6. Capability negotiation and old-server fail-closed behavior. Read-only receipt
   recovery should be introduced for supported new commands only, not advertised
   across all historical routes or existing clients.

If a future design needs proof of *non-commit*, a transactional admission/cancel
fence must also prevent a delayed original request from committing after the
check. A missing receipt alone cannot supply that fence. This larger protocol is
outside this assessment and has not been proven.

## User-visible outcomes

| Observation | Safe meaning and action |
| --- | --- |
| Matching authorized receipt | Committed; open its referenced record/history for review, without resubmitting. |
| Same key with another fingerprint | Conflict; preserve uncertainty and require review. |
| No receipt, lookup unavailable, offline or in progress | Outcome unknown; no replacement or blind retry. |
| Expired/removed receipt or different dataset incarnation | Historical outcome unknown; review original books and recovery evidence. |
| Authentication or membership denied | Cannot inspect now; prior success remains possible. Reauthenticate as the original actor and recheck access. |
| Record later changed/reversed/removed | Explain current state separately from the original command's commit evidence. |

Until prerequisites are met, use the existing manual fallback: reopen the
original company's transaction register, relevant ledger and audit history after
signing in, compare known details, and escalate unresolved ambiguity. Do not call
an ambiguous search a unique match or tell the user it is safe to create another
transaction merely because none was found.

## Storage, threat and retention limits

- No new payload, password, token, signing material or command key is persisted by
  this assessment. Do not copy current token storage into a recovery design.
- Browser localStorage/IndexedDB is not a confidentiality boundary. Even a
  non-extractable Web Crypto key does not prevent hostile same-origin script from
  using it. A passphrase-encrypted offline payload vault would require a separate
  design and would still not solve server commit ambiguity.
- Native storage must address atomic write-before-send, key loss/invalidation,
  account isolation, uninstall/backup behavior, shared-device access, logout and
  crashes at every write boundary. Silent deletion on decrypt failure is not a
  safe indication that a command never reached the server. Candidate platform
  mechanisms are separate Android Keystore-backed private storage and Windows
  local-user DPAPI, subject to packaged/unpackaged, backup/transfer, durability
  and key-loss tests. No plaintext fallback, silent eviction of unresolved
  entries, or automatic cross-device roaming should be introduced.
- Receipts and even hashes/opaque references can reveal activity or correlate
  records. Minimize stored fields, prohibit payloads in logs/URLs, authenticate
  every lookup, rate-limit discovery and prevent cross-tenant enumeration.
- Define retention before release. Receipt expiry must retain an explicit
  unknown/expired outcome or suitable tombstone; never recycle command identity
  while a delayed request/recovery remains possible. No arbitrary safe retention
  duration can be inferred from the current code.
- This is not protection against a compromised authenticated client or server,
  and does not promise exactly-once external delivery, offline saving, recovery
  of unsaved input, or synchronized company snapshots.

References: [OWASP HTML5 storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html)
[Web Cryptography security considerations](https://www.w3.org/TR/webcrypto-1/#security-considerations),
[Android Keystore](https://developer.android.com/privacy-and-security/keystore) and
[Windows data protection](https://learn.microsoft.com/en-us/dotnet/standard/security/how-to-use-data-protection).

## Verification boundary

On this exact baseline, three existing edit-retry tests and five journal-idempotency
tests passed (1.838s and 1.867s respectively). These synthetic suites cover authorization
before replay, committed requests followed by access loss, restoration of access,
current-record response semantics, period locks, rollback and retry bindings
excluded from portable backups. They do not kill/restart a browser, Android app or
Windows process and do not validate a durable recovery protocol. The small web
closure reconstruction probe likewise demonstrates state loss, not real crash
execution. No device, browser, production or external commerce action was run.
