# Offline historical integrity audit

Run `python backend/historical_integrity.py /verified-copy/company-data.json` using the backend dependencies. It reads an unpacked single-company JSON export (schema 6, 7 or 8, at most 128 MiB), hashes the exact bytes, and writes a JSON report to stdout. It does not import the application, construct a database engine, call a server, restore a company, or open a write handle. No production connection or credentials are needed. The CLI rejects duplicate JSON keys, nonfinite numbers and malformed required tables. Exit 0 means no findings in the implemented checks; 1 means findings; 2 means invalid input. Protect the output like the source books: it contains company, party and transaction identifiers.

The report compares six party-control accounts against document/settlement balances, including customer advances net of remaining advance tax, and party balances against dated ageing allocations. It identifies unlinked control journals, allocation defects, injected payment credit/advance classification metadata, backdated notes with later settlements, supplier-return reference/ITC ambiguity and excess tax components, missing provisional-return reconciliation evidence, inventory-control differences, and ambiguous stock chronology. Findings include evidence IDs and a next review action. It lists provisional source sales; it does not independently recompute every historical cost correction.

A clean report is not a statement of statutory compliance or complete historical accuracy. Journal origin recognition is heuristic. A corrupted export that omits both sides consistently can evade reconciliation. Earlier `--as-of YYYY-MM-DD` projections use surviving records and links; cancellations/amendments may have removed the original state, so use a contemporaneous archived snapshot for conclusions about that period. Original GST entitlement, supplier documents, filed returns, physical stock and device flows require separate verification. Provisional reconciliation metadata is checked for presence/linkage, not authenticated or revalued. Ambiguous pooled returns are reported rather than guessed. Audit findings must never trigger automatic journal or metadata repair.

## Review and recovery procedure

1. Preserve a verified backup and its checksum, capture the actual application/database revision, and obtain a transactionally consistent export. The audit cannot establish export completeness itself.
2. Run the auditor on a protected copy. Retain its checksum, code revision, cutoff and report. Reproduce each finding on an isolated restored copy, reconciling documents, journals, allocations, stock movements and relevant filed GST schedules.
3. Quantify proposed corrections by document, party, item, period and account. Obtain accounting review where treatment or filed-period correction is involved. Preserve an immutable before/after reconciliation; do not rewrite original documents merely to make the checks pass.
4. Before any production change, separately verify backup restoration, migration rehearsal, writer pause, exact release identity and recovery/rollback procedure. This tool neither satisfies nor bypasses those launch gates.

## Source selector quantity hints

Purchase-bill detail responses now show `remaining_return_quantity` for additional returns. Source and posted linked notes are fetched in one SQL statement, with existing ORM instances refreshed to that snapshot. Cancelled/amended quantities follow the current posting links. Ambiguous legacy matching, invalid prior references/quantities, over-returned lines or an inactive source produce null plus `return_capacity_reason`. They never appear as zero or as the original quantity. Web, Windows and Android display zero separately from “needs review”.

These hints include the currently saved note when editing; they mean **additional returns**, not the editable note's maximum. The server still validates amendments excluding their old contribution and rechecks new saves under the company write lock. A hint does not reserve stock or return capacity. Derived hint fields are stripped from posted lines. Existing APIs without hints display “needs review”; no client infers an available quantity from missing data.

## Synthetic acceptance backlog

The next cross-client acceptance scenario is a quotation with nine goods/installation lines, long descriptions, varied units, 18% GST split into CGST/SGST, round-off, warranty and terms. Verify entered values, paginated PDF totals and quotation-to-invoice conversion on API/web/Windows/Android. Record actual device and PDF visual evidence separately from automated unit/build checks. This scenario is not a statutory-validation substitute.
