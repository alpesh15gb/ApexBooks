# Reconstructed restore and logout safeguards

These changes were reconstructed after the old workspace and its unpublished commits became unavailable. They do not recreate the entire lost hardening stack.

## Restore scope

Validate payment allocation type/direction, retaining legitimate credit/debit note allocations and payments against opening balances. For posted advance/credit applications and refunds, require posted source lineage, correct direction, party/date consistency and sufficient source capacity. Applications must identify a posted target and an allocation equal to their amount. Preview and commit use the same validator before new books are created.

New tests prove wrong-direction receipts and missing advance/credit source references reject on both preview and commit without creating companies. Actual customer and supplier advance applications/refunds and credit applications/refunds export and restore successfully. Malformed source IDs, direction, chronology, party and capacity reject. The old published behavior accepts the demonstrated wrong-direction malformed backup.

Limitations: this is not the full lost restore audit. Cross-table ID/reference validation, stock movement-to-ledger valuation checks, broader historical metadata trust and adversarial balanced-journal mutations still require reconstruction. No historical books are repaired, and no production backups were accessed.

## Logout scope

The web App retains the token it accepted on mount or local sign-in. Sign out refuses to dispatch against a replacement token and rechecks token ownership after the logout request before clearing local state. Current-session logout still works. Rendered-App tests cover replacement before click, replacement during the pending response and ordinary logout; both race tests fail before this change.

This is deliberately the logout fix, not reconstruction of the lost cross-tab boundary or all authenticated-fetch scoping. Broader cross-tab stale-response protection remains outstanding. Tests use JSDOM, not a real browser or screen reader.
