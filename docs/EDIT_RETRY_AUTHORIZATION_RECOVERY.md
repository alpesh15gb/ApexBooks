# Edit recovery after an authorization change

## Reproduced contract

Synthetic API tests create and edit an estimate, sales order and posted expense. The keyed edit commits amount 150 at revision 1; treating that response as lost, the caller is demoted to viewer. The identical retry returns 403. Revoking membership returns 404. Neither denial means the earlier write failed. Restoring editor access allows the original request and key to recover without another journal entry.

If another authorized edit has since changed the record to amount 200 at revision 2, the original retry key returns that current record without reapplying the old edit. The binding identifies the operation's record, not an immutable historical response. Clients must not require the returned amount or version to equal the original submitted values.

## Client correction scope

The native document and draft edit paths must retain an already-uncertain request across subsequent errors, including authorization failures that occur before replay lookup. The original body and key remain locked for deliberate recovery. An initial definitive rejection can still permit correction. This does not change the shared policy for unrelated commands or the separate revision-only master update flow.

The pending command remains in existing in-memory ownership. No payload or credential persistence is introduced; process-death recovery is not claimed. Restored server authorization does not bypass the client's original workspace/session checks. A terminal authentication failure may still trigger the existing session teardown and discard session-owned forms. This correction does not change that security behavior or promise recovery after forced logout; its demonstrated recovery cases are role/membership denials while the original session remains active.

## Validation and remaining limits

Three backend tests cover the real API sequence, unchanged journals, restored authorization and later-edit replay behavior. They pass alongside 23 existing master, lifecycle, draft and expense tests. Native regression tests and hosted compilation are recorded with the associated checkpoint; no new actual-device execution is implied.

Windows master archive/reactivate has a separate known limitation: a lost successful response can leave ordinary unsaved-draft wording, even though a revision-protected update may have committed. This checkpoint does not claim to resolve that independent form behavior. No backend product logic, migration, OCR policy or production state is changed.

Checkpoint validation: 26 focused backend tests passed, including an independent rerun of all three new recovery cases. Four Android unit tests and 66 Windows assertions were authored for prior-unknown errors, stable request bodies/keys/routes, current-record replay and unchanged initial-rejection behavior. Native toolchains are unavailable locally, so their compilation and execution remain a hosted-CI gate. XML, diff checks and the 231-route native compatibility audit pass.
