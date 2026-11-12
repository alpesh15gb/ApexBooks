# Settled return lifecycle reconstruction

Independent review of candidate 9159cbf reproduced two previously documented fixes that had not survived workspace reconstruction:

1. A fully paid 100 invoice, full 100 credit note and later 25 refund allowed the note date to move after the refund. The resulting chronology was inconsistent and the backup failed existing restore validation.
2. Cancelling the original receipt after a full return and partial credit refund removed the original allocation but retained the return's excess credit. This reopened receivables despite the full return; the inconsistent snapshot previously passed restore validation. Supplier equivalents share the same dependency.

Both reproduced in new isolated SQLite tests before the correction. No production records were used.

## Correction

- A note with a posted credit application or customer/supplier refund cannot change its date, party identity or financial inputs. Nonfinancial headers retain the saved posting, allocation, tax and valuation data and remain editable. The rule conservatively blocks all financial changes after settlement, including earlier dates; it does not attempt to redate/recalculate later settlements.
- A payment allocated to a document with active return notes cannot be cancelled or financially amended while that dependency exists. Party-ID changes cannot bypass the financial signature. Safe receipt/payout headers remain editable.
- Adjacent note-allocation dependencies are blocked only when another active linked note has issued excess credit. Ordinary partial-note edits/cancellations that merely release return capacity remain supported. The first broad implementation failed existing partial-return tests; the narrowed guard preserves those paths.
- Restore preview and commit verify that total excess credit issued by active linked notes does not exceed capacity supported by retained source allocations and total returns. This aggregate check does not guess same-day order. POS source notes are excluded from this invoice/bill allocation invariant because POS is paid directly without a receipt allocation. Existing chronology, source, direction, capacity and ledger checks continue to apply.
- Company write locking surrounds these validations. No correction of historical books or automatic settlement reversal is performed. A rejected historical backup requires review of its original allocation/return history; do not edit JSON to force a restore.

## Tests and boundaries

Six new tests exercise customer/supplier refund and application paths; partial and fully consumed credits; partial/full original payments; atomic failed amendments/cancellation; safe note/payment headers; party-ID bypass; cancelling an unsettled return before its payment; as-of credit balances; valid backup restore; and old cancellation-path snapshots rejected by preview/commit without creating a company. Snapshot comparisons cover records, journals, lines, postings, allocation/reversal and audit/idempotency groups when exported.

The historical-bad-snapshot test deliberately disables only the new dependency helper inside its synthetic test context to recreate the formerly accepted cancellation, then requires restore rejection. This does not change runtime configuration or production behavior.

PostgreSQL regression selection includes these tests. Exact final run results are appended after completion. Earlier failed broad-guard runs remain recorded in temporary logs; they are not passing evidence. Final browser/native build/device acceptance and operator-owned production recovery gates remain open. No publication or deployment occurred.

Final verification: 366 full SQLite backend tests passed in 119.520 seconds (`/tmp/apex-lifecycle-full-final.log`). Disposable PostgreSQL 17.11 passed 18 concurrency tests, 106 reconstructed regressions including all six new lifecycle tests, five HTTP workflows and the bounded zero-error accounting workload (`/tmp/apex-postgres-return-lifecycle-final`). Earlier overbroad-guard failures were corrected before these final runs. Frontend/native code did not change in this correction; their full acceptance remains separate.
