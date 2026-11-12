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
