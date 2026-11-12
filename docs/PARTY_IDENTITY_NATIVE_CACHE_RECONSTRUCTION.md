# Party identity and native refresh reconstruction

Local follow-up to ae7e9a7, 2026-11-12. No deployment, publication or production access.

## Party identity

Master duplicate checks and document party resolution now use the same stripped Python casefold policy as imports and statements, scoped to the current company. A linked ID cannot select an unrelated party. Ambiguous historical master names reject writes and master-specific statements/balance aggregation with a review message; no historical party is merged or renamed. Opening-balance duplicate checks use the same policy. The policy deliberately does not add Unicode normalization, accent folding or transliteration.

SQLite previously ignored SELECT FOR UPDATE: four of five two-request synthetic races created both casefold-equivalent names. Its company writer guard now acquires SQLite's transaction writer lock with a no-op company update before duplicate/capacity reads. Business values are unchanged, the lock is held through the existing transaction, and authorization is rechecked after acquisition. PostgreSQL retains its row lock. The regression repeats five concurrent duplicate attempts and expects exactly one success each time. SQLite retains its single-writer/lock-timeout limitations; this is not a throughput claim.

Lookup scans company masters in Python to maintain identical semantics across SQLite/PostgreSQL. Cost is linear in master count; no new normalized-key migration/index is claimed. Legacy ambiguous books remain restorable but affected master operations fail closed until an authorized review resolves them separately.

## Native refresh

Windows inspects errors from both core reads, so a 503 cannot hide a second 403/404. Current core access denial clears Records/Banks and readiness; transient-only errors retain cache. Navigation failures occur after core success and cannot invalidate that authorized cache. Errors from a stale workspace/request/session are suppressed, including errors during awaited navigation. Android supervises both reads, applies the same denial policy and ignores stale results. Draft/editor objects are not cleared by these invalidation callbacks.

Compiled portable helper tests cover mixed failure, transient failure, stale core, navigation failure/staleness and success. Android's actual AppModel.refresh method is also extracted and JVM-compiled against controlled reads, verifying cache fields, readiness, revision and draft preservation. Full WinUI/Compose build and device behavior remain open; these helpers do not certify rendered cache/draft interactions.

## Reviewer role provisioning

`tests/provision_local_review_roles.py` runs only against an HTTP loopback origin, refuses redirects and bypasses proxies. It requires exactly one owned company named `QA Evidence Restore`, registers randomly named `.invalid` users, adds viewer/editor roles, verifies login/read access and dry-run import permissions, and checks that pre-existing membership remains. It does not post financial records or use SMTP. The generated synthetic passwords are written to a new mode-0600 JSON file, never logged; partial progress is retained for recovery.

Run from the reviewer's desktop environment (the separate loopback API is not reachable from this implementation workspace):

```sh
python tests/provision_local_review_roles.py --base-url http://127.0.0.1:API_PORT --owner-email SYNTHETIC_OWNER_EMAIL --output /tmp/apex-review-roles.json
```

The script prompts for the disposable owner password. A smoke test exercised actual synthetic API handlers through an in-process transport, verified both roles and 0600 output, and confirmed no accounting rows were created. The reviewer's requested accounts have not been provisioned by this workspace.

## Other incoming visual observations

Item-register search now says “Search item or reference”. Zero-GST item imports currently default omitted tax_treatment to taxable; explicit nil_rated/exempt/non_gst values are supported. No classification was automatically changed based only on a zero rate. Audit-event friendly labels remain an optional UX follow-up. Parent browser observations on 9159cbf are separate evidence and do not establish final-revision acceptance.

## Executed results

- Full final SQLite backend suite: **375 tests passed** in 115.685 seconds (`/tmp/apex-party-cache-backend-final.log`), after the writer-lock correction.
- Frontend: **201 tests passed**, lint passed (`/tmp/apex-party-cache-web.log`).
- Disposable PostgreSQL 17.11: **19 concurrency, 112 reconstructed regressions, five HTTP lifecycle tests** passed; bounded eight-client workload had zero errors (`/tmp/apex-postgres-party-cache`). This run preceded the SQLite-only lock branch and addition of its shared concurrency regression; PostgreSQL runtime locking behavior was unchanged afterward.
- Windows portable suite passed, including six core-refresh scenarios (`/tmp/apex-native-cache-windows.log`). Android compiled JUnit: two tests passed; actual AppModel method JVM seam: four scenarios passed (`/tmp/apex-android-core-refresh.log`).
- Provisioning smoke test: actual isolated API handlers with in-process transport, two synthetic roles, owner membership preserved, no accounting writes, mode-0600 credentials output deleted with temporary fixture.
- `git diff --check` passed. No full native build/device or final integrated browser claim.
