# Commerce retry versus worker claim: isolated reproduction

This is a test-only checkpoint, with no application correction or generation
counter. A fresh disposable PostgreSQL 17 service runs the actual retry HTTP
route and actual worker claim method against synthetic inbox and outbox rows.
Remote verification is mocked; delivery/processing is never invoked.

The test pauses retry after its company lock and claim after its message row
lock, observes retry blocked behind claim via PostgreSQL blocking PIDs, then lets
claim commit. The desired contract is a rejected stale retry (409) and the exact
worker-owned processing lease and attempts count preserved. Current code performs
a nonlocking status read followed by an ID-only update; this checkpoint is
expected to fail the desired contract if the separate reproduction confirms that
race. It does not treat an expected red assertion as a passed product test.

Both inbox/outbox directions are collected. Ordinary retry/review states must
still become pending; repeating pending retry must return409 without mutation.
These checks do not prove remote exactly-once delivery or all worker recovery.

Before migrations, the script rejects non-loopback/overridden targets and verifies
exact `apex_concurrency_test` identity, public search path and an empty user
schema through a separate read-only connection. It never resets existing data.
No production credentials or generation objects are used. Bounded JSON artifacts
record startup phases and synthetic outcomes; the workflow provides an outer
15-minute timeout. Local guard tests pass, but actual PostgreSQL reproduction is
pending this checkpoint's hosted execution. No product change should be based on
unexecuted assertions alone.

Run only with the workflow's fresh service:

    python tests/concurrency/test_commerce_retry_lease.py --output commerce-retry-evidence/result.json
