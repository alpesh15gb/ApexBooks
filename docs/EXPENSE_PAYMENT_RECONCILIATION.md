# Expense amendments and payment statement reconciliation

## Reproduced defects

An amount-only expense of INR 100 amended to INR 150 returned a successful new version but retained the old INR 100 amount and journal. The amendment classifier treated every expense as line-calculated, including expenses with no lines. The correction treats the submitted amount as authoritative only for amount-only expenses; line-based expense totals remain server-calculated. Financial amendments continue through the existing reversal/repost transaction rather than rewriting journal history.

An ordinary payment carrying an irrelevant `unallocated_credit` value could distort the party statement without changing the actual allocation or ledger. For example, a purchase bill of INR 100 and payment of INR 50 with this field set to INR 50 showed payable INR 100 in the party statement while the bill, ageing and ledger correctly showed INR 50. Ordinary receipts/payments now reduce balances by their full amount; only linked credit/debit notes use their server-derived unallocated-credit remainder. Unsupported incoming payment fields are removed, and statements also handle existing rows without rewriting their accounting history.

Omitting the amount in an amount-only expense amendment retains its existing amount, including notes-only edits. Explicit zero remains invalid. Expense-amendment retry hashing distinguishes an omitted amount from explicit zero, including line-based expense requests. Previously stored omitted-amount expense-amendment retry bindings used an ambiguous default-zero hash; those old omitted requests now fail closed with a retry-key conflict rather than replaying or posting again. Review the existing document before starting any fresh correction. Other routes and explicit-amount hashes are unchanged.

## Boundaries

These are accounting classification corrections using existing endpoints, transaction boundaries, authorization, period locks, versions and retry keys. They do not add a schema migration, new payment method, deferred expense liability, automatic tax claim or new client capability. Expenses remain fully paid when posted; unpaid supplier liabilities use purchase bills and separate settlements.

Verification uses isolated synthetic data. Production records, main, deployments and devices are unchanged. A separately reproduced inward-workbook paise/ITC allocation discrepancy is not fixed by this checkpoint.

## Verification

- Eight new focused expense/settlement tests passed. Independent cross-review caught and verified the omitted-amount and retry-hash compatibility corrections before checkpointing.
- Full backend: 267 tests passed. Web: 169 tests, lint and production build passed without client changes.
- A separate 48-document synthetic matrix covered three tax profiles, inclusive/exclusive prices, discounts and rounding; all exact retries and ledger totals reconciled.
- Five isolated HTTP workflow tests and a 6,402,963-byte complete-backup roundtrip in 13 bounded chunks passed, retaining archived evidence hashes. Focused tests also verified corrected reports after both legacy JSON and complete ZIP restore.
- Native contract audit: 232 routes matched. Nine backup-target and 21 deployment-management mock tests plus simulated backup/restore safety checks passed. The encrypted infrastructure-backup CLI check was not run locally because `age` and `age-keygen` are unavailable.
- No new native or device code was required. Hosted CI, including PostgreSQL, remains the next checkpoint gate; local evidence is not a live-data or deployment proof.
