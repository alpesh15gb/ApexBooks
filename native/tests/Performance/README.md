# Native monthly-chart performance

This is a bounded presentation-only optimization. It does not change record loading, API requests, accounting postings, company/session boundaries, register pagination or report readiness.

## Algorithm

Both native charts previously scanned the complete loaded record list once per displayed month, then folded each month's sales and purchase values. The helpers now build the same ordered month buckets and traverse the records once. Each bucket receives additions in the original record order, with the same decimal types, kind signs, posted filter, inclusive date bounds and month-prefix matching. Android's existing `remember` keys and complete-history gate remain unchanged. No persistent or cross-company cache is added.

A 50,000-row, eight-month fixture reduces record-predicate visits from 400,000 to 50,000. This is an operation-count improvement, not a claim that an actual device screen renders eight times faster.

## Reproducible proxy

`python3 native/tests/Performance/month_aggregation_probe.py`

This independent Python/Decimal model compares the previous repeated scan with a single scan over synthetic invoices, POS, returns, purchases and nonfinancial rows. It asserts equal totals. One local seven-run median was 62.08 ms versus 17.08 ms. Results vary with machine load. This is explicitly **not** Kotlin, .NET, Android hardware, WinUI or browser timing evidence.

## Native verification gate

Native reference-equivalence tests retain the old algorithms as oracles and check date/year boundaries, missing or unposted data, credits/debits, empty periods, decimal values, output ordering, input immutability and a 50,000-row fixture. The optimized code is wired into the existing charts without changing the surrounding UI.

At this local checkpoint, Android SDK/Gradle and .NET toolchains are unavailable. Native tests are authored, not locally executed. Compilation, unit tests and application builds must pass hosted CI before treating this as a verified native release. No device permission or test run is implied by the Python proxy.

A separate read-only review found no blocking difference for the application's ISO-dated records. One theoretical Windows distinction is explicit: the previous prefix predicate used culture-sensitive `StartsWith`, while bucket lookup is ordinal. Invalid date strings containing culture-ignorable Unicode are outside the server's ISO date contract and are not claimed equivalent. Project XML and the 232-route contract audit pass; these checks do not substitute for native compilation.
