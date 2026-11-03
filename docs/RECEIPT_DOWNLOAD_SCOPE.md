# Receipt download session and refresh scope

A mock-only deferred-response probe found that receipt downloads could dispatch
a file after the authentication token changed during body verification or hashing.
The API session guard protected response headers, but not the later verification
await. A separate probe found Refresh receipts aborted dispatch yet left the
Verifying button disabled because the old operation's guarded cleanup no longer
owned the new list scope.

The download operation now retains its original token, list scope and controller
identity and checks all three before/after response verification and before file
dispatch. Observed token/clear storage events abort and invalidate that download;
restoring the token does not revive it. A fresh explicit download is required.
Refreshing the receipt list resets its download indicator, while old completion
cannot clear a newer download's state. Object URLs are revoked even if dispatch
throws or is invalidated after allocation.

Existing company/unmount abort behavior, checksum/size validation and viewer
permission to download are retained. No receipt upload/archive operation,
financial posting, backup transfer or global session behavior is changed.
Cancellation cannot retract a file already dispatched before a switch. Silent
same-document token ABA without an observed event is not a claimed guarantee.

All evidence uses synthetic bytes, mocked read responses and intercepted anchor
clicks. No real receipt upload, browser action or user file is involved. The
original pending upload approval remains separate.

Verification: 25 new scope tests and six existing attachment tests pass. A focused
five-case run against original f914506 produced four failures (token change during
stream/hash and Refresh during each stage) and one successful viewer-download
control. The complete 295-test web suite, lint and production build pass. These
are mock-only component tests, not actual browser download acceptance.
