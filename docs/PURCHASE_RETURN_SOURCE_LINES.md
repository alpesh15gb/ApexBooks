# Explicit purchase-return source lines

Purchase-bill responses now annotate each line with `source_line_id`, `source_document_id` and `source_line_number`. A line ID combines its source-local index with a fingerprint of its saved financial values (item, quantity, prices, discounts, GST classification/treatment and computed taxable/tax values). It is derived on read, including for legacy bills; no existing book row or database schema is modified. The separate document ID is remapped during backup restore, while the fingerprint remains valid.

Debit-note clients copy these references when loading a bill. Web, Windows and Android provide a source-line selector showing original line number, description, source quantity, GST rate and ITC treatment. Selecting a line replaces that row's identity and inputs; GST classification/rate/ITC are inherited, while quantity, price and discount remain editable subject to server limits. Reopen preserves the reference. Native source changes clear old rows before loading. The web's independent option loader ignores stale responses and offers retry without replacing the draft.

The API verifies the selected bill belongs to the company and is posted, checks the reference against its current financial values and item, derives GST/ITC from that source, and bounds cumulative quantity, taxable value and tax by the chosen source line. Duplicate rows in one note count together. The company write lock serializes concurrent returns. Source references are included in amendment intent; financial amendments revalidate after removing their own old posting, and cancellation releases capacity. Existing document-level tax-component and amount limits remain additional guards. Preview derives source treatment; final save additionally checks cumulative capacity under the write lock. A preview is not a reservation.

Compatibility policy:

- Legacy requests with one matching source line automatically acquire explicit lineage when item identity matches.
- Older requests without references may still use a pool of matching lines only when GST rate, supply classification and ITC treatment agree. Their aggregate source quantity/value/tax is bounded.
- A later explicit selection that overlaps a historical ambiguous pooled return is blocked for review. The system does not guess how that earlier note was allocated. Overlapping explicit and pooled groups in one request are rejected. Missing, negative or nonfinite historical line quantities/values also fail closed rather than freeing return capacity.
- Description-only legacy lines retain their prior matching behavior. Explicit references bind item identity; display descriptions are refreshed from the selected source line.
- New selectors require source references from the updated API to distinguish otherwise identical mixed-treatment lines. An older API does not provide the new guarantees. Deploy the reviewed API before distributing these client builds.

Selectors show **original source quantity**, not live remaining capacity. Save checks the current remaining balance. Historical incorrect ITC, metadata or postings are not repaired. The read-only review and correction process remains in `STOCK_RECONCILIATION_REVIEW.md`.

Validation added: API mixed-service and same-stock-item treatment, partial/full reversals, duplicate-row and source-line caps, invalid/stale references, amendment/cancellation, header preservation and restore; web exact selection/reopen payload; Android in-place selection identity and serialization/reopen; PostgreSQL competing returns against one source line. Native build checks do not replace device acceptance of these selectors, especially Windows interaction and Android navigation/accessibility.
