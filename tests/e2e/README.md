# Isolated end-to-end checks

Install `backend/requirements-dev.txt` and run `npm ci` in `frontend` first.
On Windows, Linux or macOS, the Python runner starts its own API and Vite on
available loopback ports, migrates a disposable SQLite database, runs both HTTP
suites and stops only its own processes:

```sh
python tests/e2e/run_local.py
```

For desktop/mobile browser acceptance, use the same Playwright version as CI
and its matching Chromium runtime:

```sh
python -m pip install playwright==1.64.1
python -m playwright install chromium
python tests/e2e/run_local.py --browser --artifacts /path/to/test-artifacts
```

Include `--presentation` to run the populated UI acceptance matrix too. It scans
all entry forms on phone and desktop, all reports and settings categories, six
dashboard widths from 320 to 1920 px, and keyboard drawer/menu and dialog scrolling
behaviour. The pinned `axe-core` development dependency checks WCAG A/AA rules;
screenshots, accessibility JSON and a trace are retained with the accounting evidence.

On Linux, use `python -m playwright install --with-deps chromium` to install its
system dependencies too. For a focused rerun, `--browser-only` skips the two HTTP
suites but still creates fresh servers and books. Browser runs compile a fresh
production bundle into the disposable workspace and serve it through Vite preview
with the real API proxy. This tests the shipping assets without waiting on cold
development-module transforms; `frontend/dist` and running dev servers are not
changed. HTTP-only runs use Vite's development server. The default bundled Chromium
is recommended. `--browser-channel chrome` or `msedge` instead launches that
installed browser with a new isolated headless profile, never the user's current
browser session. The runner refuses external API overrides and excludes inherited
OCR/commerce/database secrets. Browser channel selection is explicit, so a stale
`APEX_BROWSER_CHANNEL` environment value cannot silently change this runner.

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

`browser_workflow.py` drives desktop registration/company creation, invoice
entry, empty cancellation/reopening, unsaved-edit navigation, partial payment,
register/ageing balances, PDF/XLSX downloads, estimate/recurring-template creation
and logout. It asserts that the first input survives on both document and
recurring-template forms. A separate 390px mobile context checks layout, empty
dismissal, first-input retention and dirty-draft confirmation.

Verified locally on Windows on 2026-11-03: the production-bundle runner passed
both HTTP suites and the complete desktop/mobile browser gate with Playwright's
bundled Chromium. Earlier development-server runs could stall on pending source
module transforms; those failed attempts are not counted as browser passes.
This browser-emulation result does not claim native Android/Windows GUI coverage.

The Python runner above is the cross-platform entry point. The existing shell
runner also supports the browser gate:

```sh
APEX_BROWSER=1 APEX_PYTHON=/path/to/venv/bin/python tests/e2e/run-local.sh
```

Use `--artifacts` with the Python runner, or `APEX_E2E_ARTIFACTS` with the shell
runner, to choose the evidence directory. The Python browser runner otherwise
retains a dedicated system-temp evidence directory and prints its path; the
temporary database is always removed. Evidence includes screenshots, synthetic
PDF/XLSX downloads and Playwright traces. Failures add the page HTML, URL,
outstanding requests, console/page errors and invalid form controls. API/Vite
logs are retained too. These files contain only the synthetic local accounts and
books created for this run. Both success and failure traces can be opened with
`python -m playwright show-trace /path/to/desktop-trace.zip`.

Optional local latency sample: `APEX_PERF=1 APEX_PYTHON=/path/to/python bash tests/e2e/run-local.sh` seeds 100 invoices and prints 20 sequential samples per endpoint. This is not a hosted load test.
