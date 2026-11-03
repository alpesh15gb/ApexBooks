# Manual journal and reversal retry recovery

## Confirmed behavior and scope

Previously, identical manual journal requests returned success once, then a reference conflict. Identical reversal requests returned success once, then an already-reversed conflict. Even requests carrying an idempotency key behaved this way because these routes did not use it. A later accounting-period lock prevented recovering the original response. Unique references and reversal links prevented duplicate accounting in the tested concurrent cases, but clients could not safely resolve a lost successful response by retrying.

The change adds durable command bindings for manual journal creation and reversal. It does not change balanced-line validation, company/account ownership, inventory-control restrictions, reversal history or period-lock rules for a new posting.

## Contract

- Capability: `journal_idempotency`.
- Updated clients require verified support and send `Idempotency-Key` with an immutable command body.
- Keys are scoped to company and operation: journal creation or reversal of a particular original journal. Reusing a key with a different request on the same operation is rejected.
- A command binding, journal, lines, reversal link where applicable, and audit event commit atomically. Failed transactions retain neither a partial journal nor a successful command binding.
- Membership/write authorization is checked before looking up a successful replay. An authorized exact replay returns the original response before applying the current period lock, because it creates no new posting.
- Keyless older clients retain their existing behavior and limitations. Updated clients must not silently fall back to unprotected submission on an old or unverified server. Coordinate the API migration and client rollout.

Inputs, original company/session, date, reference, accounts/amounts and reversal target remain captured during an unresolved request. Retrying does not replace the body or key with edited values. Known current-attempt rejections are explained separately from an unknown transport outcome. A successful earlier request may still exist after an interrupted response, so reconciliation guidance must not falsely promise that nothing was saved.

## Migration, backups and limits

The additive `JournalCommand` table retains indexed command identities, request hashes, the resulting journal identity and the original small response. Its company/journal relationship is constrained. No secrets or full draft payloads are stored in it.

Portable company backups retain journals, reversal links and audit history, but do not carry operational retry bindings into a new company with new IDs. A command from the source company must not be replayed as a posting in the restored company. A database backup is still required for operational recovery of the original command namespace. Downgrading the schema refuses to discard populated command bindings and acquires a writer/table lock before checking emptiness, preventing a concurrent successful command from being lost. Apply migration `i018fa586ba3` before starting this API version. During an application rollback, retain the additive table and a database backup; an older API does not provide this recovery capability, so updated clients must keep journal posting disabled rather than silently fall back.

Client retry protection is bounded to the supported live application/session lifetime. This change does not add a durable client command journal or claim crash/process-death exactly-once recovery. No new device run, signing, production schema migration or deployment is performed by local verification.

## Verification

The initial synthetic review verified five concurrent period-lock/post interleavings: either posting completed before the lock, or it was rejected after the lock. Moving a lock backward was rejected, and an open-period reversal of a locked original remained valid. Journal/reversal duplicates created one original and one reversal, remained balanced, and portable validation passed.

Final local verification:
- Full backend suite: 259 tests passed; eight focused API/migration tests passed.
- Independent review reproduced the original downgrade race and verified its correction. Exact create/reversal replay after period locking, different-body rejection, route scope, single concurrent posting, rollback, authorization-before-replay, company/journal foreign keys and portable backup handling passed.
- The pinned original repository baseline `1e8d981149e8a4dce597ec49933b33887bcf00d6` upgraded to `i018fa586ba3` in isolated SQLite. Original 33 tables, record IDs and report values were preserved; readiness changed from migration-required to ready, repeat migration was unchanged, evidence/complete-backup roundtrip passed, and the pre-upgrade SQLite backup reopened with the original app. This is not a production clone or PostgreSQL upgrade proof.
- Web: 169 tests, lint and production build passed, including 11 journal tests for capability gates, frozen retries, reconciliation and malformed success acknowledgements.
- Five isolated HTTP workflow tests and a 6,402,971-byte complete-backup roundtrip in 13 bounded chunks passed. Native API route scan: 232 matched.
- Six Android test methods and 53 Windows assertions were authored for journal command identity, capability checks, conflict recovery, malformed replies and session isolation. Local native toolchains are unavailable; compilation and execution remain pending hosted CI. No new device run is claimed.
- A PostgreSQL concurrent keyed journal/reversal and post-lock replay regression was added and syntax checked, but not run locally. PostgreSQL migration locking was inspected and mock-tested, not executed against a local PostgreSQL server.
- Nine backup-target and 21 deployment-management mock tests, plus simulated backup/transactional restore safety checks passed. The encrypted infrastructure-backup CLI test was not run locally because `age` and `age-keygen` are unavailable.

All new fixtures are synthetic. No main-branch, production data, live migration, deployment, signing or permission changes were performed. Hosted verification of the new immutable checkpoint remains required.
