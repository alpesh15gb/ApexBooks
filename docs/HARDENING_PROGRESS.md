# Hardening work log (2026-11-02)

Research basis: [official competitor workflow comparison](PRODUCT_RESEARCH.md).
The priority is financial correctness and recoverable daily workflows, not visual
imitation or invented statutory capabilities. This log is updated as checks run;
see CI for the exact published revision rather than assuming working-tree results
apply to a later change.

## P0 findings implemented with regression tests

| Finding | Fix / evidence |
|---|---|
| Untracked lines could inject inventory cost and post phantom COGS/inventory | Server removes client valuation fields and computes tracked cost itself; `test_accounting_integrity.py` |
| Amount-only expense could inject input tax/rounding | Server owns calculated fields and disregards irrelevant payment/transfer fields; same regression suite |
| Stock adjustment/opening ignored native retry headers | Atomic optional retry-key replay/conflict handling while preserving legacy keyless calls |
| Malformed amendment allocations returned server errors | Shape/amount checks return actionable validation rejection; no partial posting |
| Rounded invoice amount could overflow stored money precision | Reject rounded overflow before writing |
| Restore capped allocation per invoice, not per receipt | Validate source-payment total as well; `test_restore_integrity.py` reproduces rejected 110-from-100 allocation |
| Restore party comparison differed from posting | Same trimmed, case-insensitive comparison preserves legitimate exports |
| Late register load could overwrite latest results/company | Generation + latest-request scopes; web component/unit coverage |
| In-flight save allowed mutable form/cart and duplicate click | Freeze posting draft and guard synchronous duplicate submission; web component coverage |

## Active P0 acceptance work

- Preserve exact command/body after an unknown network outcome across all clients.
- Enforce locked periods for asynchronous commerce returns as for normal postings.
- Native company refresh/sign-out/navigation scope guards and native regression/build jobs.
- Isolated import/reconciliation of four owner-supplied Vyapar backups; private data
  and detailed reports stay outside source control.
- Live local HTTP lifecycle coverage, and browser automation on a supported runner.

## Evidence recorded so far

- Baseline: 76 discovered API tests, seven web helper tests, production web build.
- First integrated checkpoint: 83 discovered backend tests + 12 web tests, build,
  180 native route literals against freshly generated OpenAPI, simulated database
  backup/transactional restore checks passed.
- Subsequent API integrity checkpoint: 85 backend tests passed.
- Live local HTTP: registration, company, invoice, replay, collection, overpayment
  rejection, ageing, balanced reports, PDF/XLSX, cross-tenant denial and logout
  revocation passed via Vite → FastAPI with disposable SQLite.
- No live deployment or production database was used in these checks.

## P1 follow-through and boundaries

Receipt/advance, invoice settlement, and bank match must stay separate in labels
and balances. Printing/export must remain read-only after posting. Source drafts
must preserve conversion linkage without posting stock or revenue. Report filters
must match screen and downloaded file. These existing capabilities are being
verified rather than replaced with a second accounting engine.

Do not mark native install/print/share, real PostgreSQL concurrency, offsite restore,
real-browser acceptance, or statutory readiness passed solely from unit tests or
static route compatibility. See [release gates](RELEASE_CHECKLIST.md).
