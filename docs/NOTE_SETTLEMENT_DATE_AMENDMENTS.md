# Note amendments retain settlement chronology

A credit/debit note could previously be financially amended to a date later than
an already-posted application or refund. For example, a paid source document of
100, a note of 100 dated April 2, and a refund of 40 dated April 3 allowed the
note to move to April 4. At April 3 the credit report then showed zero available
credit while the customer/supplier credit ledger showed −40. New settlement
creation already rejected a settlement before its note; amendment omitted the
corresponding chronology check.

Financial amendments now find the earliest **posted, same-company**
`credit_application`, `customer_refund` or `supplier_refund` linked by
`credit_note_id`. A proposed note date after that date is rejected with HTTP 422:

> Revised note date cannot follow an existing credit settlement; choose YYYY-MM-DD or earlier

The guidance names the earliest settlement date. Equality is allowed. The check
runs before replacement posting, journal reversal, stock or allocation mutation.
No histories are rewritten, and unrelated/unposted records do not establish this
constraint. This does not introduce a new party-change policy.

Authorization, exact-key replay, stale-version and period-lock checks retain their
existing order. In particular, a previously successful exact retry still replays
after a period is locked; a fresh invalid date is a correctable 422. Clients must
continue retaining an earlier unknown financial outcome rather than treating a
later rejection as proof that nothing was committed. There is no new API field,
capability, migration or automatic adjustment of dates.

Local synthetic regressions cover tracked sales and purchases, both applications
and refunds, same-day amendments, exact retries, stale versions, period locks,
viewer/foreign-company scope, unposted/foreign linked rows, unchanged journals,
reversals, stock, allocations, retry bindings and reports on rejection. JSON and
complete ZIP restore preserve note/settlement dates, remapped links, stock values
and financial balances. These tests are not a live-data repair or audit claim.
