# Master form session boundary

## Reproduced scope

A standalone party or item editor could be opened under one signed-in session, then submit its original fields and revision under a replacement token written by another tab. Full-app synthetic tests reproduced this for ordinary edits, archive and reactivate. Revision checks prevent stale overwrites, but do not bind an already-open form to its originating actor.

## Correction

The form retains its original session identity in memory and checks that identity before invoking its save callback. A changed or missing session blocks the save without discarding entered fields. Restoring the exact original session allows the user to retry deliberately; the server still checks membership, role and revision. No credentials or form payloads are newly persisted.

This is not durable master-write idempotency. A master update whose response is lost may already have committed; its original revision can subsequently be rejected. Review the original company's current master before deciding whether another change is needed. A fresh login token is not treated as the original session, even for the same account.

## Verification boundary

Full-app synthetic deferred-response tests cover actor replacement, field retention and original-session restoration. They are not a real-browser or device execution claim. No API, schema, OCR policy, production setting or main-branch change is part of this correction.

The focused suite has five passing full-app tests: edited master, archive and reactivate replacement-session rejection with original-session recovery; the already-protected draft editor; and a late master error followed by a retained-input revision conflict. The complete web suite passes 229 tests, lint and production build. Native edits are a separate checkpoint.
