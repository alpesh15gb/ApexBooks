# Isolated PostgreSQL acceptance

These checks create synthetic users and companies. Never use a hosted database,
production credentials, or a tunnel to production.

Install `backend/requirements-dev.txt` into the local Python environment. Obtain
the PostgreSQL server binaries from the [official PostgreSQL download page](https://www.postgresql.org/download/).
On Windows, its advanced ZIP download links to the [EDB binary archives](https://www.enterprisedb.com/download-postgresql-binaries).
Extract a binary archive under ignored `tmp` or supply an existing installation's
`bin` directory. The runner uses the executables only, not its existing data.

```powershell
.venv/Scripts/python.exe tests/concurrency/run_local_postgres.py `
  --pg-bin tmp/postgres-qa/pgsql/bin `
  --artifacts tmp/postgres-release-evidence
```

Add `--browser-business` to build the current frontend into the runner's isolated
working directory and run the full web trading journey against the same
PostgreSQL-backed API. This requires frontend dependencies and Playwright's
Chromium runtime (`python -m playwright install chromium`). It uses default
headless Chromium, clears inherited browser selection, and starts an owned
loopback Vite preview proxy that is stopped on exit. Browser assertions, trace,
and screenshots are retained beneath the evidence directory.

The runner creates a new password-protected cluster under `tmp`, binds it to an
available loopback port, and creates only `apex_concurrency_test`. It discards
inherited database, PostgreSQL connection and integration credentials. It starts
two owned Uvicorn workers and stops those workers and its cluster on exit. It
does not install services or change host permissions. Logs and the stopped
synthetic cluster are retained for diagnosis; no password is written to evidence.

The acceptance stages are:

- Concurrent idempotency, conflicting retry payloads, number allocation, payment
  and split-allocation caps, competing document edits, cancellations, cancellation
  versus receipt, stock, auth session revocation, recurring drafts, immutable
  attachments and complete-backup upload/restore. A deterministic report/write
  interleaving verifies that first-time account creation cannot split the
  financial statement or trial balance across different database snapshots.
- Real HTTP lifecycle checks for sales, purchases, partial receipts, returns,
  bank matching, reconciliation, advances and refunds, exports, roles and tenant
  boundaries against the actual PostgreSQL-backed API.
- With `--browser-business`, real web form entry for purchases, mixed goods and
  services, GST and discounts, partial payments, stock returns,
  expenses and cancellations, with exact final stock and accounting assertions.
  Only master data is seeded through the API for this browser journey.
- A bounded real HTTP sample, by default 300 invoices with half payments, 30
  expenses, 60 interleaved report reads and eight concurrent clients, followed by
  ten retry replays and 30 credit notes with stock returns. `load.json` records
  measured latency, throughput, errors and final accounting invariants. This is
  a local sample, not a guarantee of production capacity or external-service latency.

The stock race intentionally permits two sales against one available unit and
asserts the resulting quantity **-1** and carrying value **-60**. Negative-stock
billing is supported; it must retain every movement and provisional cost rather
than silently dropping a sale. See `docs/NEGATIVE_STOCK_BILLING.md` for replenishment
and valuation behavior.

For an already provisioned **disposable loopback** CI PostgreSQL database, the
existing entry point remains:

```sh
APEX_TEST_DATABASE_URL=postgresql://test-user:test-password@127.0.0.1:5432/apex_concurrency_test \
  python tests/concurrency/test_postgres.py
```

The database name and loopback hostname are enforced by the test script. That
entry point does not create or destroy the database; CI must own its lifecycle.
