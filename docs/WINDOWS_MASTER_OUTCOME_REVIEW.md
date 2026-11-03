# Windows master changes with an unconfirmed outcome

## Reproduction and server contract

An existing party or item can be archived successfully while its PUT response is lost. Previously, the Windows editor returned to an ordinary editable form whose close prompt said the draft had not been saved. That statement was not justified by a timeout.

Synthetic API checks confirm that an archive at revision 0 can commit as inactive revision 1. Repeating the original request, even with the same Idempotency-Key, returns a revision conflict: master updates use compare-and-swap, not durable idempotency. Role removal can instead return 403 or 404 before that revision check. A later explicit reactivation at revision 1 produces active revision 2; the original request cannot overwrite it. These master changes create no financial journal entries.

## Bounded correction

The existing-master editor retains its originating company, session, workspace, master identity and submitted values in memory. An uncertain outcome requires review and disables further Save attempts in that editor. It does not automatically repeat the write, adopt a fresh revision or infer success by comparing current values.

Entered values remain visible. Closing requires an explicit warning that the change may already have saved, with **Keep open** and **Close and review** choices. Users can copy any needed values before closing. Reviewing the current master is a read, not proof of which request produced that state. A later deliberate change starts from a newly opened current revision.

Fresh definitive validation rejections still permit correction. Existing financial pending-command close protection remains ahead of the optional master review prompt. New-master creation and unrelated dialogs are unchanged. A refresh after explicit close applies only to the original workspace if it is still current.

## Limits

This is in-session recovery guidance, not durable master-write idempotency or process-death recovery. Existing authentication teardown may remove session-owned forms. No new secret or payload persistence, backend behavior, migration, OCR policy or production setting is introduced. Native compilation and real hosted UI evidence must be reported separately from authored transport tests.

## Checkpoint evidence

The native suite adds 69 authored transport assertions covering archive/reactivate timeouts, no second PUT, fresh validation correction, malformed success metadata, later valid revisions, concurrency, company/session replacement, and revision-only servers that omit unsupported lifecycle fields. Source/XML/diff checks and the 232-route compatibility audit pass. Independent review checked the server contract and unchanged financial close-guard ordering. These native assertions and WinUI compilation have not run locally because .NET is unavailable; hosted CI remains required. The new close-review interaction has not been exercised on an actual Windows desktop.
