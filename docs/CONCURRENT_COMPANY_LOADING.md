# Concurrent company loading

The register API currently uses bounded offset pages. A second client can post a
new transaction or move a document between pages while another client is loading
history. Overlapping pages must not be silently appended or deduplicated: the
former can count a transaction twice, while the latter can conceal missing rows.

The client guard tracks record IDs within each full scan. On an overlap it discards
the scan and restarts from the first page once. A second overlap stops with a clear
refresh error, without publishing partial history. Stable loads keep the normal
500-row page size and request count. Existing workspace guards still prevent obsolete-company responses from replacing
the active company. The web loader also checks cancellation before each request. A previously confirmed register may remain
visible with a refresh warning; that is not a claim that it is current.

## Verification

The web regression inserts a new invoice after page one of a 1,001-row history.
The unguarded loader returned 1,002 rows but only 1,001 unique IDs, omitted the new
invoice and repeated an old invoice. The guarded scan returns the exact current
1,002 unique rows after one restart. Repeated overlaps fail after four requests;
company changes during an overlapping response do not restart an obsolete scan.

Commands: `cd frontend && npm test && npm run lint && npm run build`.
All 114 web tests passed for the paging-only change, plus lint and production build.

Android and Windows use the same discard/restart-once rule. Their loopback transport
regressions cover an insertion across pages, repeated overlap, duplicates within a
short page, and the unchanged 1,250-row / three-request path. These new native tests
are authored but not yet executed: the local Android SDK/Gradle and .NET toolchains
were no longer available. Compilation and native test execution remain required
before publishing or deploying this follow-up. Earlier native green CI applies to
the previous source, not this change.

## Limits

This is an overlap-corruption guard, **not a transactional snapshot or realtime
synchronization protocol**. Concurrent deletions or changes that do not produce
an overlapping ID can still shift or mix pages. A future snapshot/revision API
must cover financial allocations as well as records and preserve tenant isolation.
Do not replace this guard with silent deduplication or claim full consistency.

This change does not add persistent retry storage. Financial command recovery
across full process death remains separate work requiring secure, account/company-
scoped storage and truthful reconciliation of uncertain server outcomes.
