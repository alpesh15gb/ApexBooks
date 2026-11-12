# Reconstructed safeguards: PostgreSQL and reference follow-up

Published draft #59 is fc415d654e0f1a4afd2c335a2b1202586ec1c695, whose tree exactly matches local d66c5449b069a313dccd20f19722dfbe48b3f1b1. That approved upload completed; nothing was merged or deployed. The corrections below are subsequent local work.

## Additional restore corrections

Reject any stock movement whose source is marked cancelled. This closes a zero-cost physical-return bypass that combined cancelled=true with a missing credit and overstated line/movement quantity. Valid API-cancelled purchases, with reversed journals and no movements, remain restorable. Tests exercise malformed preview and commit atomically and actual valid cancellation/restore.

Require explicit top-level party and bank references to resolve within the snapshot, including bank transfer destinations and reconciliation reviews. Explicit source_document_id must match a conversion link, or an imported immediate payment verified against its retained full-posting archive (source document, mapping, kind, date, amount, advance status and party). A marker alone is insufficient. The initial stricter conversion-only rule broke valid import backups; the final compatibility regression covers missing references, forged mapping/digest/flag and valid report-preserving restore. Name-only historical parties, implicit default banks and absent conversion metadata remain compatible; embedded historical source archives are not recursively interpreted as current local references. Both reported cancelled-stock and newly identified reference bypasses reproduce against d66c544's prior validator.

## Disposable PostgreSQL evidence

Used PostgreSQL 17.11 from signature-verified Debian packages extracted under /tmp, with no system installation or service changes. The existing runner created a new password-protected loopback cluster, cleared inherited database/integration credentials, ran two API workers and stopped all owned processes afterward. Final evidence: /tmp/apex-postgres-reference-compat-final. Initial verification before the last explicit-reference changes: /tmp/apex-postgres-reconstructed.

Final run:
- 17 PostgreSQL concurrency tests passed.
- 69 reconstructed restore/return/import compatibility tests passed on the PostgreSQL engine.
- Five real HTTP accounting lifecycle tests passed.
- Eight-client bounded workload: 20 invoices, 20 partial receipts, two expenses, two stock-return credit notes, ten idempotent replays; zero errors.
- Financial balance difference 0.00; trial debits/credits both 9442.00; receivables 1062.00; inventory 102 units valued at 6120.00.
- PostgreSQL log confirms clean shutdown.

These are synthetic consistency/regression checks, not a production restore rehearsal, load-capacity guarantee, statutory filing validation or physical-device acceptance. Existing books were not accessed or repaired. The local test runner and optional flag preserve this verification path for future batches.

Published PR #59 CI: eight successful checks (synthetic, browser, PostgreSQL concurrency, Windows/Android client builds, Windows UI smoke and both unsigned release builds). Local device acceptance was skipped. These results cover d66c544, not the later local corrections.

Final full SQLite backend run: 333 tests passed in 102.104 seconds; log /tmp/apex-reference-full-final.log. No frontend code changed after d66c544.
