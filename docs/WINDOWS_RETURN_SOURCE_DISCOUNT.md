# Windows manual return source discount

The Windows document editor's contextual return action already initialized the source document's percentage discount. Selecting the same source bill manually from a new debit note copied its lines, party and tax state but left the document discount at zero.

Synthetic reproduction: a line at 100 with a fixed discount of 10 and a document discount of 10% has taxable value 81, GST 14.58 and total 95.58. The manual selection path instead proposed 106.20 and posting rejected it as exceeding the source. Preserving the header percentage previews and posts at 95.58 for both pending-review and ineligible input-GST classifications.

Both Windows initialization paths now use the same source-discount helper. Selecting another source without a header discount resets the field to zero. Subsequent explicit user edits remain possible. Source lines, fixed discounts, input-tax treatment and inclusive-tax flags are not changed. This patch does not copy absolute round-off values or automatically prorate fixed discounts.

Five portable assertions cover the source percentage, missing/default/reset values and source JSON immutability. They are authored for the hosted native suites; local .NET compilation and runtime execution were unavailable when this checkpoint was prepared. The financial payload reproduction and shared API/web aggregate checks passed locally. No new device run, production change, migration or API contract change is included.
