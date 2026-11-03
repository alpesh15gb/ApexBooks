# Master edits: explicit revision required

> Breaking edit compatibility: this change is a separate, locally verified follow-up
> to the published 1.5 candidate. Coordinate API and client rollout before deploying.
> An old client that omits the revision cannot safely edit parties or items.

## Why

Two clients could open the same item at sale rate 100. Client A saved 120, then
client B changed purchase rate using its old form and silently restored sale rate
100. A stale party or item form could also reactivate a master that another client
had archived. Both outcomes were reproduced through the actual HTTP API using
isolated synthetic records before adding the revision check.

## Contract

`PUT /api/companies/{company_id}/masters/{master_id}` requires the explicit original
master revision as the top-level `version` field. Existing masters without a stored
revision are revision zero. The value must be a nonnegative integer, not a boolean,
string or fractional number. The server compares it under the company mutation
lock and advances it only on a successful update. Missing or stale revisions return
409 with update/reload guidance; malformed revisions return validation errors.

New versions are returned in the master record's `data.version`. Clients must keep
the revision from the form they opened, not fetch a new revision immediately before
saving and attach it to old values. A conflict must preserve the user's unsaved
inputs and require an explicit reload/review. Never silently merge financial rates,
archive state, payment terms or delivery details.

Reads and new master creation remain compatible. Unversioned edit requests are
intentionally rejected, including requests from previously supported older native
clients. The API advertises `master_edit_revisions` in `/api/capabilities`. New clients
fail closed for edits when that feature is missing or unverified, including against
an old API that would ignore `version`. A transient check failure offers Retry and
keeps the open form; verified unsupported APIs require an update. Creates and reads
remain available. A capability declaration does not bypass server enforcement. Imported and
restored historical records begin from their stored revision or zero.

## Retry and rollout limits

A response lost after a master update may produce a stale-version response on retry.
The user must reload and compare the saved details; this is not an idempotent master
write or an exactly-once guarantee. Financial document retry contracts are unchanged.

Before rollout, distribute compatible web/Windows/Android clients and confirm their
configured API target. Keep the new API off production until that compatibility
transition is explicitly coordinated. No database migration or live deployment is
performed by the source change itself.

## Verification status

Isolated HTTP regressions cover stale sale prices, stale archive/reactivation,
missing and malformed request revisions, malformed stored revisions, legacy-zero
reads, ignored forged create revisions, tenant isolation and viewer restrictions.
A PostgreSQL two-writer test requires exactly one success, one conflict, one audit
and the winning revision. That new race test is **not yet run locally** because
PostgreSQL/Docker is unavailable; it must pass in the dedicated CI service.

Rendered web tests cover original-revision submission, retained typed inputs after
409, old/404/unverified APIs refusing edits, continued new-master availability, and
explicit transient-feature retry without replacing the original form revision.

Android/Windows sources and focused transport/retry/capability tests are prepared,
but their new compilation and tests remain **pending CI** because local native
SDK/toolchains are unavailable. Earlier green native results apply to main's prior
source, not this follow-up. The checked-in OpenAPI snapshot was regenerated from
the isolated current application, including previously shipped additive routes.

Final isolated aggregate check passed: 189 backend tests, 118 web tests, web lint/build,
5 HTTP workflow tests, one 6.4 MB / 13-chunk complete-backup restore, 231 native route
matches, 9 backup-target mocks, 21 deployment-preflight mocks and simulated backup
transaction safety. The real `age` infrastructure-backup test was not run locally
because `age`/`age-keygen` were unavailable. Mock readiness output does not describe
or contact production. PostgreSQL and native compilation remain the gates above.
