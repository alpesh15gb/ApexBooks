# Cross-client release checklist

This is a verification checklist, not a claim of statutory certification or zero bugs.
Work starts from source commit `1e8d981`; older acceptance/implementation documents
linked in the original README were not included in that checkout. Do not treat
those missing files, the bundled OpenAPI snapshot, or a successful deployment as
proof that this source revision passed acceptance.

## Reproduce isolated checks

```bash
python -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
npm ci --prefix frontend
PYTHON="$PWD/.venv/bin/python" bash scripts/check.sh
APEX_PYTHON="$PWD/.venv/bin/python" bash tests/e2e/run-local.sh
```

`check.sh` rejects `ACCEPTANCE_BASE`, runs all discovered backend tests in a fresh
SQLite database, frontend unit/component tests and production build, native route
checks against OpenAPI generated from the **current API**, and simulated database
backup/restore checks. Encrypted backup tests require `age` and `age-keygen`.
The HTTP runner creates a separate disposable SQLite database, starts both Vite
and FastAPI, and exercises the real proxy/API rather than mocking network calls.
Neither command needs production credentials or writes hosted accounting data.

## Required acceptance matrix

| Area | Automated evidence | Remaining acceptance beyond local automated tests |
|---|---|---|
| Sign-in, session expiry, recovery, tenant/role boundaries | API auth and recovery tests; HTTP register/login/logout + second-tenant denial | Native credential vault, interrupted login and expiry UI on actual OS |
| Sales, purchases, GST modes and estimates/conversion | API/completion suites, frontend line-item helpers | Review legal tax classifications and business-specific invoice fields |
| Receipt/payout allocation, advances, credit/refund | API/completion/commerce tests; HTTP invoice collection and ageing | Explain advance versus invoice settlement consistently in all clients |
| Stock, valuation and adjustments | API/completion/integrity suites | Historical source reconciliation for each migration; no silent negative-stock normalization |
| Journals, balances and period locking | API accounting tests and HTTP balanced reports | Accountant review of source openings and accounting policy |
| Bank matching and reconciliation | API tests, restore round trips | Actual bank CSV formats and signed reconciliation review |
| Reports and PDF/XLSX | API exports + native branding tests; HTTP file bytes | Real printer, PDF viewer, share sheet, fonts and page layout on Windows/Android |
| Retry safety | API replay/conflict regressions, frontend submit tests | Device process death/network interruption and same-request recovery |
| Company switching/navigation | Frontend request-scope and component tests | Native back/forward/dismiss and interrupted navigation UI acceptance |
| Company backup/restore | API round trip, allocation validation, simulated database restore | Real encrypted offsite retention and clean-host restore rehearsal |
| Shared native API contract | Current generated API versus native route literals | Payload/method/runtime compatibility; static paths alone are insufficient |
| Web packaging | Vite production build | Browser end-to-end on a supported browser runner |
| Native packaging | Dedicated native build/test CI where configured | Signed release install, app update and actual-device acceptance |
| Vyapar migration | Disposable rehearsal of each distinct backup, financial and stock reconciliation | Owner-confirmed destination/company identity before live import |

## Invariants the release must preserve

- No posted document, payment, stock movement, or journal is duplicated by retry.
- Client-supplied calculated tax or inventory fields cannot alter server-ledger rules.
- Each journal balances; each allocation is positive, same-party, date-valid, and
  within both the document balance and source payment/credit amount.
- Rejected writes leave no partial journal, stock, sequence or allocation effects.
- Locked periods and viewer permissions apply on the API, not only disabled UI.
- A stale response cannot reopen a signed-out session or replace a newer company.
- Export, printing, draft/hold, and reconciliation matching do not repost cash.
- Restores create a new company; credentials/team access are never imported.

## Deployment boundary

The repository describes Vercel as a preview and `apexbooks.in` / `api.apexbooks.in`
as a separate production installation, potentially sharing hosted PostgreSQL.
Do not use either for synthetic test writes. Branch publication and a draft PR do
not imply a production deployment. Before live release: verify the deployed source
SHA, tested backup/restore, migration compatibility, secrets/HTTPS, native version
compatibility, and a reviewed rollback strategy. Ordinary domestic GST workflows
are not e-invoice/e-way-bill/portal-filing integrations and must not be advertised
as such. Production backup monitoring and statutory review remain explicit gates.

## Read-only live audit follow-up (2026-11-12)

- Live GSTR-1 monthly → Sales register retained monthly dates under the financial-year label. Local Reports restores ordinary dates and has a passing rendered quarterly/company-switch regression. Verify the final integrated release on monthly and quarterly transitions; deployment has not occurred.
- Live Sales invoice summary split paise onto a second line at 1200×790. RegisterOverview now uses the responsive nonbreaking FinancialFigure with wider adaptive cards. Run `cd frontend && node tests/registerFigures.browser.mjs` for synthetic seven-plus digit values at 1200, 768, 375 and 320px. Local Chromium execution is blocked by socket permissions, so visual acceptance is pending, not passed.
- Bind displayed company/date/party and downloadable report scope to the successfully applied report snapshot, including delayed responses and failures.
- Verify explicit period-lock date review; keyboard-only nine-line invoice entry; actionable validation linked to fields; dialog focus, return focus and status announcements; 320px reflow. These are acceptance criteria, not newly demonstrated defects.
- Evaluate a server-calculated invoice subtotal/tax/discount/round-off bridge, a non-destructive negative historical cash explanation, searchable state-code/name choices, a compact party-ledger summary and unambiguous date hints. Preserve stored state codes, dates and imported balances. GST worksheets must remain distinct from filed returns.

### Subsequent local visual fixes

- RecordEditor source banner names the actual edited or converted target type, including estimates. Fourteen rendered editor regressions passed, covering eight edit types and estimate-to-invoice conversion; frontend lint passed.
- Day book excludes recurring_template, restore_marker, document_branding and vyapar_backup_archive alongside masters. The source estimate and generated estimate remain in rows/count; posted financial totals remain zero for these drafts. Twelve Day book/recurring regressions passed.
- Journal-history voucher labels/source links remain a follow-up UX task. Preserve authorization and correct cancellation/missing-source handling when implementing it.

These fixes still need final integrated visual acceptance; the isolated desktop reviewer was previously exercising 71aca43.

- Reorder now retains a company-scoped PO-created confirmation and an Open purchase order action after saving, including refresh. It explicitly keeps the low-stock recommendation because a draft does not add stock. Twenty-six rendered accounting/editor/workspace tests and lint passed. Confirm this save-to-worklist path in the integrated desktop preview. Pending incoming quantity is not inferred from draft POs; any later quantity display must distinguish unconverted drafts from confirmed or partially received orders.
