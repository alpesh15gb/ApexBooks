# Isolated end-to-end checks

Install `backend/requirements-dev.txt` and run `npm ci` in `frontend` first.
From the repository root:

```sh
APEX_PYTHON=/path/to/venv/bin/python tests/e2e/run-local.sh
```

The runner creates and migrates a disposable SQLite database, starts FastAPI and
Vite together, tests through Vite's real HTTP proxy, and removes its temporary
files on exit. Ports 18080 and 15173 must be free (override with APEX_API_PORT/APEX_WEB_PORT). It overrides `DATABASE_URL` and
never reads production credentials. The Python test refuses non-loopback hosts;
do not run it separately against a local tunnel to a live database.

Coverage: registration, login, company creation, invoice calculation, retry-key
replay without a duplicate posting, partial cash collection, overpayment
rejection, receivable ageing, balanced trial balance and financial report,
PDF/XLSX export signatures, cross-tenant access denial, and revoked-session denial.
The second lifecycle covers purchases, supplier payout, linked debit/credit returns,
tracked stock quantities/cost, bank statement deduplication and matching,
reconciliation reviews, customer/supplier advance applications and refunds with
retry replay and over-refund rejection, settled ageing and balanced profit reports.

## Browser acceptance (separate gate)

HTTP coverage is **not** browser acceptance. A separate CUA cloud-browser pass
verified registration, company creation, Cancel/reopen invoice, 251.00 invoice,
100.00 receipt, 151.00 remaining balance in register and ageing, PDF and XLSX
downloads, and logout. One Chromium renderer crash was recovered by reload;
this is not evidence that all browser scenarios or devices have passed.

To launch a fresh isolated workspace for browser testing:

```sh
APEX_PYTHON=/path/to/venv/bin/python tests/e2e/serve-local.sh
```

Open `http://127.0.0.1:15173`. Ctrl-C stops the servers and removes synthetic data.

On a computer where the browser and local servers share a network namespace,
repeat these checks with synthetic data:

1. Register, create an unregistered company, and verify the dashboard.
2. Open a sales invoice, cancel/close it, reopen, and verify no record was posted.
3. Enter two units at 125.50, save once, and confirm a 251.00 invoice. Repeat a
   submission while delayed to verify only one record exists.
4. Apply 100.00 cash, verify 151.00 outstanding, and reject 152.00 overpayment.
5. Open ageing/financial reports, PDF and XLSX exports; confirm the displayed
   balances agree with the posted records.
6. Switch companies while a form/request is pending, use Back/Forward and Escape,
   and verify no stale records appear in the new company.
7. Sign out and verify protected views do not remain usable; sign back in.
8. Repeat document entry and Cancel/Close on a narrow/mobile viewport.

## Automated browser gate

`browser_workflow.py` mirrors the observed desktop flow and adds a 390px mobile
layout/dismissal check. Install Python `playwright` and `python -m playwright
install --with-deps chromium`, then run:

```sh
APEX_BROWSER=1 APEX_PYTHON=/path/to/venv/bin/python tests/e2e/run-local.sh
```

Set `APEX_E2E_ARTIFACTS` to retain screenshots and synthetic PDF/XLSX downloads.
The script was syntax-checked in this executor; it has not yet run as a complete
Playwright job. Do not equate the manual CUA pass with this CI gate passing.

Optional local latency sample: `APEX_PERF=1 APEX_PYTHON=/path/to/python bash tests/e2e/run-local.sh` seeds 100 invoices and prints 20 sequential samples per endpoint. This is not a hosted load test.
