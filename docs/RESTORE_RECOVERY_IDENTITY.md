# Complete-company restore identity and consistency

## Corrected behavior

A restored company can itself be backed up and restored. The new copy retains ancestral restore markers for history, but those markers must not override its own restore identity. Previously, a fresh upload of the same nested archive to the same target name could create another company because recovery examined only the first marker.

Recovery now uses the company's local `backup.restored` creation audit event. Imported events are retained as `backup.source_event`, so an ancestor's digest cannot identify the current copy. The current owner and exact target name bound this lookup. A different target name intentionally creates a separate copy; a different archive is not silently substituted.

For legacy companies without a local creation audit, a single restore marker remains supported. Multiple ambiguous markers produce a controlled 409 asking the user to review the existing company, rather than guessing or creating a duplicate. No existing records or audit history are rewritten.

Direct legacy restore now reserves the SQLite writer before checking recovery identity, matching the serialization already used by staged transfers. PostgreSQL retains its user-row lock. Identity lookup and new-company creation share the transaction; a failed restore cannot leave a partially created copy.

A completed staged transfer rechecks current access to its restored company for status, preview, commit replay and begin-request replay. A current viewer can recover the read-only result. A user who no longer has access cannot recover it through an old transfer ID. These checks match the existing recovery-list behavior.

Reconciliation reviews must reference a bank present in the archive or the default bank. Invalid references are rejected during preview, before creating an inaccessible restored review.

## Verification

Synthetic tests cover:

- Nested export/restore followed by a fresh transfer of identical bytes and the same target name, returning the existing company.
- Ancestral digest separation, intentional differently named copies and safe legacy fallback versus ambiguous history.
- Concurrent direct legacy restore producing one company, plus an authored PostgreSQL equivalent.
- Archived evidence bytes and hashes, unchanged source company, exact staged replay, revoked access and current-viewer recovery.
- Invalid reconciliation references rejected before creation, with valid named-bank remapping, statement-import deduplication, archived party and opening-balance links retained.
- Existing atomic evidence-insert failure and successful retry tests.

No schema migration, new client contract or device permission is required. Existing JSON/gzip and complete ZIP formats remain supported. PostgreSQL execution is a hosted CI gate; local SQLite checks are not a substitute. No production database or supplied company backup is used in this review. This is server-side restore recovery, not a claim of durable recovery for every financial client command after process death.
