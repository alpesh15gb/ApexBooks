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
