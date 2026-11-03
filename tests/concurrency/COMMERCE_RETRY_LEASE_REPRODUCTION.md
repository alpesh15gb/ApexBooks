# Commerce retry versus worker claim: isolated reproduction

The original reproduction checkpoint was test-only, without an application
correction or generation counter. The current branch adds the narrow CAS
correction described in ../../docs/COMMERCE_RETRY_LEASE_CAS.md; generation
instrumentation remains absent. A fresh disposable PostgreSQL 17 service runs the actual retry HTTP
route and actual worker claim method against synthetic inbox and outbox rows.
Remote verification is mocked; delivery/processing is never invoked.

The test pauses retry after its company lock and claim after its message row
lock, observes retry blocked behind claim via PostgreSQL blocking PIDs, then lets
claim commit. The desired contract is a rejected stale retry (409) and the exact
worker-owned processing lease and attempts count preserved. The original code performed
a nonlocking status read followed by an ID-only update; its hosted run confirmed
the race in both directions. Corrected code must pass the same desired contract.
The original red assertions are not relabeled as passed product tests.

Both inbox/outbox directions are collected. Ordinary retry/review states must
still become pending; repeating pending retry must return409 without mutation.
These checks do not prove remote exactly-once delivery or all worker recovery.

Before migrations, the script rejects non-loopback/overridden targets and verifies
exact `apex_concurrency_test` identity, public search path and an empty user
schema through a separate read-only connection. It never resets existing data.
No production credentials or generation objects are used. Bounded JSON artifacts
record startup phases and synthetic outcomes; the workflow provides an outer
15-minute timeout. Local guard tests pass. Original PostgreSQL reproduction completed with the
expected failures; corrected PostgreSQL verification remains pending its own
hosted execution. See the correction document for exact original run evidence.

Run only with the workflow's fresh service:

    python tests/concurrency/test_commerce_retry_lease.py --output commerce-retry-evidence/result.json
