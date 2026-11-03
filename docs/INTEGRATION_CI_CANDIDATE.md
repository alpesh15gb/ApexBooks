# Integration candidate: CI only

This candidate combines main `2d9d1ef5a2ab72138463aff2221b34715b4d6989` and PR24 `79dd15370a43d112570a48040e3e4593fd630297`, with common ancestor `87833e3d12b68130b78883a5364e30e749768985`. It is not a production release or authorization to deploy.

The two textual conflicts were resolved by retaining both the main bubble-phase dirty-input handling and stacked inline party/item editors, and both release-evidence sections. Nonconflicting changes from both parents remain. The upgrade checklist now identifies migration head `i018fa586ba3`, including journal-command downgrade restrictions.

## Unresolved OCR transport decision

Main's existing explicit `OCR_ALLOW_INSECURE_HTTP=1` compatibility code is retained unchanged for integration testing. This does not approve enabling it, determine the provider's HTTPS support, or establish the live setting. The transport policy is undecided and live configuration is unknown. No credentials/configuration were fetched or changed and no OCR images or credentials were transmitted in preparing this candidate.

HTTPS remains the default. The explicit opt-in permits public HTTP transport of the provider authorization and document bytes without TLS. Existing conflicting documentation that says this override is unsupported must be reconciled only after the transport decision; this candidate does not silently choose a new policy. The validator, caller, VPS preflight and transport tests must remain aligned.

## Acceptance limits

Combined-tree local synthetic backend/web/deployment-mock tests are separate from hosted PostgreSQL and native compilation/runtime acceptance. Earlier PR24 green checks and Android run50 do not establish this combined tree's device behavior. Old clients require a coordinated rollout for master-edit revisions, conversion-source revisions and exact bank-unmatch revisions. Provider database mapping, full-database recovery rehearsal and signed distribution remain release prerequisites. Ambiguous staggered subset-return budgets remain fail closed; no allocation is invented.
