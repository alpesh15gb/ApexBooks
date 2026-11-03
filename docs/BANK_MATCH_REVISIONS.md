# Compare-and-unmatch reconciliation safety

## Confirmed failure

An exact bank statement match could be removed using only its statement-line ID. If one client read a match to transaction A, another client removed it and matched transaction B, the first client's stale DELETE silently removed B. The same sequence could follow a lost successful DELETE response and retry. Journals were not duplicated, but the newer reconciliation decision was lost.

## Protected operation and rollout

Exact-match removal now requires a JSON body containing the displayed `expected_record_id` and integer `expected_match_revision`. The API compares both under the existing company write lock. Revisions count the immutable live match/unmatch audit events for that company and statement line. Removing and rematching the same transaction changes the revision, so the protection also covers an A → unmatched → A sequence.

The statement list exposes `match_revision`; the capability is `bank_match_revisions`. Web, Windows and Android must verify this capability before sending an exact unmatch. An unavailable capability check requires retry; a verified old server requires an update. Clients capture the displayed company, line, transaction and revision rather than fetching a fresh token immediately before the destructive action.

**This changes compatibility.** Older clients that omit the required body are rejected with update guidance. Coordinate API, web and installed native updates before rollout. An optional token would leave older clients capable of silently erasing newer matches, so there is no unsafe fallback. This draft change is not deployed to production.

A stale command, including a retry after an earlier success, receives a conflict and cannot remove a later match. It does not silently choose a replacement transaction. Existing allocation deletion uses its immutable allocation ID and is unchanged. Transfer posting, allocation amounts and financial journals are unchanged.

## Backup and identity scope

Portable restore creates a new company and new statement-line IDs. Previous audit events remain retained source history, not live mutation events. Consequently restored lines start at revision zero in their new identity scope. A source-company command cannot apply to a restored company or another tenant. No database migration or new credential is introduced.

## Verification status

The initial bounded review used synthetic data only:
- Cash-to-bank, bank-to-cash and bank-to-bank transfers, including named/default banks, balanced correctly.
- Exact and simultaneous identical transfer retries created one transfer; foreign/same-account and invalid direction/amount requests were rejected without journals.
- Concurrent duplicate imports retained row multiplicity without duplication; dry-run did not write, and an invalid mixed batch rolled back.
- Concurrent allocations could not consume more than the posted bank transaction.

Final local verification:
- Full backend suite: 251 tests passed; 14 focused tests passed. Coverage includes stale replacement, ABA, lost-response replay, competing removals, strict payload validation, authorization, allocation-ID compatibility and both portable restore formats.
- Independent read-only review passed the backend and web focused tests with no remaining concrete defect. Match identity and revision are read in one SQL snapshot, not assembled from separate queries.
- Web: 158 tests, lint and production build passed.
- Five isolated HTTP workflow tests and a complete-backup HTTP roundtrip passed, retaining evidence through a 6,402,976-byte ZIP in 13 bounded chunks.
- Native contract scan: 232 routes matched. Four Android tests and 20 Windows assertions were added for captured intent, malformed revision, capability gating and company/session isolation. Native compilation and execution remain pending hosted CI because local toolchains are unavailable.
- A PostgreSQL regression covers competing removals, rematching, stale retries and ABA without changing journals. Its syntax checks passed; PostgreSQL execution is pending hosted CI.
- Nine backup-target and 21 deployment-management mock tests, plus simulated backup/transactional restore safety checks passed. No deployment was executed. The encrypted infrastructure-backup CLI check was not run locally because `age` and `age-keygen` are unavailable.

No live bank data, production action, browser action or new device permission is involved. Older clients and servers must follow the coordinated rollout requirement above; this checkpoint is not a production rollout.
