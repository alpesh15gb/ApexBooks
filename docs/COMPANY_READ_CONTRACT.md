# Reject incomplete company reads instead of showing empty books

## Reproduced failures

A syntactically valid HTTP 200 response is not sufficient proof that a company page was loaded. The web collector accepted rows with missing, numeric or blank IDs. Windows converted a non-array response to an empty array, including at later offsets. Android filtered non-object array entries out before checking page length, so a malformed 500-entry page could become 499 rows and falsely end the scan.

These are malformed-response handling defects, reproduced using synthetic inputs and source-tied traces. They do not establish that the normal API emits such responses.

## Bounded read contract

Record pages must be arrays of at most the requested 500 rows. Each row must be an object with a nonblank string ID. Exact IDs are preserved; no trimming, UUID requirement, kind whitelist or rejection of extra fields is introduced. Invalid envelopes or rows reject the entire scan before it is published as complete. Existing duplicate-page detection still restarts once and fails closed on repeated overlap.

The normal current and original 1.3 APIs satisfy this contract. Company and bank lists also use string identities; the built-in bank ID `default` remains valid. Strict validation must not change permissive JSON helpers used by unrelated views.

Existing workspace/sequence checks continue to discard stale completions. A failed same-company refresh retains previously confirmed records with an error instead of replacing them with an empty or partially fetched list. An initial failed load is unavailable, not proof that the company has no transactions. Authentication/access revocation handling remains separate and authoritative.

## Evidence and limits

The web contract suite covers invalid first/later pages, page-size bounds, malformed rows/IDs, duplicate overlap, cancellation/scope changes, empty final pages and preservation of future fields/exact identities. Independent probes verify prior confirmed records are not overwritten by a failed scan. Eighteen web contract cases pass. Five Android test methods and 78 Windows assertions are authored against the production read helpers; local native toolchains are unavailable, so hosted compilation/unit checks are required. No new device UI proof is claimed.

No financial write, persistent cache, API schema, OCR policy, production setting or historical record changes are included. Dashboard unavailable-state and company-scoped document-preference controls are separate UI corrections.
