# Recover settlement saves after a balance refresh

## Reproduced failure

An advance application/refund or note-credit settlement can commit while its response is lost. A concurrent refresh can then report zero remaining balance. Android previously froze form inputs but reconstructed the endpoint/body from a newly filtered source row: retry could fail locally because the source was no longer selectable, or change the party name under the original idempotency key. Web advance/credit screens could hide their retry form after the same refresh while the global pending-write guard continued blocking navigation.

The fixes keep an unresolved command recoverable independently of the refreshed selectable balances. They do not create a replacement transaction or infer an unconfirmed result from a changed balance.

## Safety boundaries

- The original route, serialized values and idempotency key are reused. First submission still requires a valid available source.
- Android retains the command only in the existing ViewModel-owned in-memory tool draft. Original company/workspace checks prevent submission or UI completion in a replacement workspace; concurrent clicks do not issue another request.
- Android verifies the returned record identity, posted status, kind, date, amount, source and applicable target before releasing the unresolved command. Malformed success remains unconfirmed.
- Web recovery is an explicit original-save retry, not a rebuilt operation against the current catalogue. Refresh alone cannot hide that recovery control. A settlement-specific acknowledgement check inside the retained operation verifies the posted result before releasing it; valid leading-decimal amounts remain compatible with server parsing.
- No financial payload is written to disk/localStorage by this change. Full process death, expired sessions and durable offline recovery are not solved.
- A rejection after an already-unknown attempt does not establish whether that earlier attempt committed; the command remains protected, including after membership or validation rejection. A fresh validation rejection still permits correction.
- Server membership/role, remaining-balance and idempotency checks remain authoritative and unchanged. No OCR policy or live setting changes are included.

## Verification

Pre-fix synthetic jsdom tests reproduce disappearing web retry controls after zero-balance refresh. A source-tied Android proxy reproduces the missing-source/changed-name reconstruction; this is not Android device execution. Eight authored native command unit tests cover frozen replay, source disappearance/rename, workspace replacement, concurrent clicks and malformed responses; local native compilation is unavailable and hosted CI is required.

Separate backend review passed 16 existing serialization/access/settlement regressions, customer and supplier split payments (70 allocated 40/30), replay after period locking without extra journals, changed-body rejection and cross-company/role/revoked-access rejection. Eight customer/supplier advance/credit apply/refund variants returned identical JSON on immediate replay. Backend idempotency is company/key scoped, not actor scoped; it does not authorize a client to replay an uncommitted intent under a different signed-in identity.
