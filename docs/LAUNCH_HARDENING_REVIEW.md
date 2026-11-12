# Launch hardening review — 12 November 2026

This follow-up starts from `ee18418b542125092a0fe76eb8aa84055c68e351`.
It is a bounded engineering review, not statutory certification or a claim that
all possible defects have been eliminated. No production books were changed.

## Corrections

- Registered company detail edits can no longer remove the GSTIN while retaining
  the registered tax profile. Failed edits preserve the original company.
- Registered outward invoice/POS/credit-note serial numbers accept only letters,
  digits, slash and hyphen within the existing 16-character limit. This applies
  to new documents and header-only amendments; supplier references and historical
  reads are not rewritten.
- Tax invoices to registered buyers dated from 1 April 2021 require HSN/SAC on
  every line. An unregistered buyer's taxable supply of INR 50,000 or more requires
  the recipient address. The threshold uses taxable value, not tax-inclusive
  invoice total. Header amendments cannot bypass these checks. These are minimum
  guards, not automatic legal tax classification. Turnover-dependent HSN length,
  broader address/state validation and special supplies still need review.
- Company and party/item edits now retain changed-field before/after values in
  the operational activity log. Image changes record hashes rather than image
  payloads. This improves evidence but is not external, tamper-resistant audit
  retention or statutory audit-trail certification.
- Company-detail saves have synchronous duplicate-submit protection, pending and
  dirty-dismissal handling, and protection against stale company responses.
  Both regular and composition forms expose required GSTIN/state fields.
- Period locking now requires explicit review of the date before a forward-only
  lock is submitted, with pending/stale-response protection.
- Branding saves/uploads/removals are scoped to the active company, freeze the
  draft during submission and block navigation while posting. Late responses
  cannot replace another company's bank/signature form state.
- The portable PostgreSQL runner uses loopback TCP without depending on a
  system-owned Unix socket directory or a socket-capable workspace mount.
- A follow-up rejects malformed party GSTIN/state-code inputs before posting,
  normalizes surrounding whitespace/case and rejects disagreement between a
  registered supplier's GSTIN prefix and supplier-origin state. Purchases retain
  the effective origin in their snapshot. Header amendments cannot silently
  switch supplier identity to another state while retaining the old tax split;
  an explicit origin correction follows the normal financial amendment path.
  A buyer's GSTIN state is not forced to equal the delivery/place-of-supply state.
  These are format/consistency checks, not government GST-registration verification.

## Independent local evidence

All accounting data used below is synthetic and disposable.

- Final `scripts/check.sh` passed: 267 backend tests, 154 frontend tests, ESLint,
  production build/bundle budgets, five live local HTTP workflows, current native
  route contract checks, nine backup-target tests, 32 deployment-controller tests,
  and simulated database/backup safety checks, including encryption.
- Five new backend regressions cover GSTIN edits, serial validation and audit
  changes. Five more cover invoice requirements and scope boundaries.
  A further five cover malformed tax locations, normalized identifiers,
  supplier-state consistency and safe financial amendments.
- Ten new frontend component regressions cover company editing, period locks
  and branding.
- PostgreSQL 17.11: 16 concurrency tests and five HTTP accounting lifecycle tests
  passed. The subsequent bounded load run used two API workers and eight clients:
  300 invoices, 300 partial receipts, 30 expenses, 30 stock-return credit notes,
  60 report reads and ten idempotent replays. It recorded zero errors, matching
  trial-balance totals of INR 57,630, stock of 130 units valued at INR 7,800, and
  zero balance-sheet difference. This is not a production capacity guarantee.
- Dependency audits found no known vulnerabilities in the backend requirements
  and frontend production dependencies at review time.
- Encrypted backup safety checks passed with real `age` encryption and simulated
  database/remote storage. This is not proof of a deployed offsite backup.
- The repository's legacy SQLite migration/restore rehearsal passed. This is not
  an actual production database clone or PostgreSQL upgrade rehearsal.

The current cloud environment could not complete a fresh full browser matrix;
component/build results do not replace browser or native-device acceptance.
Historical browser screenshots and test claims apply to their recorded revision,
not automatically to these edits.

## Production boundary

Public health/readiness returned version 1.5.0 with build
`98e4750ca84757a09415247cf9c97b5fc623fae9` during this review. The user reported
staging `1.5.0-ee18418b542125092a0fe76eb8aa84055c68e351` without restarting services.
Neither revision contains the follow-up changes above. Publish and stage the
final reviewed commit before attempting its cutover.

Follow [the deployment guide](DEPLOY_AND_BUILD.md): verify a real full-database
recovery point and isolated restore, preserve keys/settings, identify and pause
all writers (including other deployments), review schema/recovery compatibility,
and verify exact served and container identities after cutover. Never invent
the upgrade-plan attestations or substitute a company export for full database
recovery. No production cutover was performed by this review.

Indian Accounting Standards/AS applicability, accounting policy choices and
statutory special cases remain business-specific. The existing README's scope
limits (including depreciation, NRV write-downs, reverse charge, cess, exports,
e-invoicing/e-way bills and filing) are not removed by these fixes.

## Follow-up: control-account and provisional-return containment

Two synthetic regressions failed before these guards: a manual debit to SYS-AR
was accepted without a party allocation, and a five-unit sale from zero stock,
followed by a five-unit purchase at INR 60, could be returned at zero inventory
cost. A balanced trial balance alone does not detect either misstatement.

Manual journals now reject receivable/payable, customer/supplier credit and
customer/supplier advance control accounts on either side. Linked document
workflows remain responsible for their subledgers; existing manual journals can
still be reversed through the audited reversal endpoint. Historical divergence
must be identified and corrected separately; this does not repair old books.

Physical returns against provisionally valued negative-stock sales now fail
closed in ordinary credit notes and deferred commerce receipts. Financial-only
credits remain available. This is containment, not a completed valuation fix:
there is no supported workflow yet to allocate later replenishment variances
back to source sales and finalize their return cost. The guard also rejects
unreplenished provisional sales. Do not clear flags or edit stored cost fields
manually to bypass it. A full solution must cover partial/multiple receipts and
returns, same-day ordering, cancellations, locked periods and restore replay.

No schema or production changes were made. Production database recovery,
isolated restore, writer pause, migration compatibility, exact release identity
and recovery procedures still require real operator evidence. No new statutory
compliance conclusion follows from these accounting tests.

## Follow-up batch: API, web and native workflow integrity

The isolated branch `fix/control-account-guards` preserves the previously tested
PR tree. Changes after the initial containment commit include:

- Purchase debit notes derive input-tax treatment from the matched source line,
  and cumulative returns cannot exceed source pending/ineligible tax. Mixed
  treatments with ambiguous line identity fail closed rather than guessing.
- HTTP record inputs cannot set unallocated credit or advance tax event metadata.
  Payment party reports ignore inappropriate historical unallocated-credit fields.
  Previously saved spoofed GST metadata still requires a historical-data review.
- Notes dated before existing settlement allocations are rejected atomically.
  Later settlements are not silently rewritten.
- Cancelled documents cannot download an apparently active PDF in any layout.
  Retained records and audit history remain available; cancelled-copy PDF design
  is not supplied by this containment change.
- Web bank-review/create/allocation operations have synchronous in-flight guards
  and scoped responses. Commerce receipt quantities reset when selection changes
  and only visible credited products enter the payload. GST-to-ordinary reports
  restore the prior date range; company-specific party filters cannot leak.
- Reopened financial-only notes preserve `return_stock=false`. Invoice quick-add
  master requests freeze editing, close and submission, use synchronous guards,
  ignore stale editor responses and link items by line object identity.
- Web, Windows and Android manual-journal selectors omit protected control
  accounts. Native journal dialogs request discard confirmation for dirty input.
- Android period locking has explicit load/error/retry gating and confirmation of
  the selected date. Android and Windows cash-book exports use the last successful
  displayed report's filters, including after subsequent edits or load failures.

Verification for this batch: the full backend suite passed 274 tests, the full
frontend suite passed 160 tests, and web lint/build/bundle budgets passed.
After strengthening tests, seven accounting guards and three rendered filter/race
checks also passed. Current API/native route checking found 256 route literals
against 121 contract paths with zero unmatched references. These contract checks
are not compilation or device acceptance.

Native UI changes are source-reviewed only in this environment: Windows/.NET and
Android SDK toolchains and physical devices are unavailable. Delayed/failed native
loads, stale responses, export consistency and discard dialogs still need compiled
native automation and real device acceptance. No new PostgreSQL concurrency run,
full browser matrix, statutory review or production restore rehearsal was performed
for this batch. Production and the remote draft PR were not changed by this local
implementation. Negative-stock source cost reconciliation remains unfinished.
