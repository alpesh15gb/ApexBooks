# Everyday features: shared API contract

All paths below start `/api/companies/{company_id}`. All reads require company
membership; metadata changes use the existing owner/editor master routes. No new
roles, schema migration, external services, or automatic accounting postings.

## Low stock

Item `data.low_stock_threshold`: decimal string or null; nonnegative, at most
three decimal places, maximum 999999999999.999. Requires tracked goods. Null
disables. Existing clients omitting the field on PUT preserve the saved value.

`GET /reports/reorder?as_of=YYYY-MM-DD` (defaults to server today):

```
{as_of, total_low_stock, rows: [{item_id, name, unit, on_hand,
 low_stock_threshold, suggested_quantity, purchase_rate, valuation_status}]}
```

All quantities/rates are decimal strings. Rows flag quantity <= threshold.
`suggested_quantity=max(threshold-on_hand,0)` is a draft starting point, not an
order. At exact threshold it is zero: the user must enter a positive quantity.
`valuation_status` is `valued`, `unvalued`, or `negative`. Quantity comes from
dated stock movements, not cached master quantities. Review a purchase order
before saving; metadata edits and the report do not change journals/valuation.

## Party terms

Party `data.payment_terms_days`: integer or null, 0–3650. Null means no default;
zero means same-day. Existing clients omitting the field preserve its value.

`GET /parties/{party_id}/due-date?document_date=YYYY-MM-DD` returns
`{party_id,payment_terms_days,document_date,suggested_due_date}`.

Use only for a new untouched/default-derived date. Never overwrite manually
entered, imported, amended or converted document dates. The server never
silently applies terms or changes prior invoices/bills.

## Explicit last-price suggestions

`GET /parties/{party_id}/item-prices?item_id={id}&side=sales|purchase`:

```
{party_id,item_id,side,default_rate,history:[{record_id,number,date,line_index,
 quantity,rate,price_includes_tax,gst_rate,discount_percent,discount_amount}],
 suggested_rate,suggested_price_includes_tax,
 source:"last_posted"|"item_default",requires_confirmation:true}
```

History is bounded to the last five matching lines from posted sales invoices/
POS or purchase bills, using exact saved party/item IDs. Drafts, returns and
reversed posting journals do not supply prices. No matching historical name is
guessed. Historical rate is shown with its original inclusive/exclusive tax
basis and discounts; Apply explicitly selects rate+basis, not tax eligibility
or a hidden discount. With no history, the item's side-specific default rate is
suggested. Changing party/item must invalidate a pending older request.

Defaults survive portable export/restore. SQLite integration tests cover
precision, zero/null behavior, historic stock dates, purchases/returns,
leap-year due dates, manual override retention, isolation and viewer denial of
writes. PostgreSQL JSONB/history and compact-list parity are CI gates.

## Master lifecycle and delivery address

`party` / `item` master data now includes `is_active` (strict boolean, default
`true`; missing legacy data means active). Parties also accept
`shipping_address` (string, maximum 500 characters, default empty). Use the
existing `PUT /masters/{id}` with the current master fields to archive/reactivate
or change the address. Omitting either new field preserves its previous value.
There is no deletion: list/detail, reports, history and existing print snapshots
retain archived identities. Member write authorization is unchanged.

New documents, drafts, POS and conversions reject inactive selected masters,
including exact-name free-text matches. Reactivate before converting an archived
party/item source. Historical draft/posted amendments may retain identities that
were already present, but cannot introduce another inactive master. Linked
receipts/payments and return notes remain possible, as do existing advance and
credit settlements: archiving must not strand debt. New advances and new party
or stock opening balances require active masters. Stock adjustments remain
available for inventory correction. Reorder suggestions exclude inactive goods.

New sales invoices, POS, estimates, proformas and sales orders copy the party's
shipping address only when the submitted document omits `shipping_address`.
An explicitly empty or manually entered address is preserved. Changing a master
never changes an existing document's shipping/billing address or print snapshot.
Backups preserve both fields; restore rejects invalid optional field types or
oversized addresses while accepting older backups that omit them.

## Warning-only customer credit limits

Party master `credit_limit` is an optional nonnegative decimal string (15 digits,
2 meaningful decimal places). Missing/null disables warnings; zero is valid.
Existing master PUT omission preserves the value; explicit null clears it. Items
cannot have a credit limit. Import/export/restore preserve and validate it.

`GET /parties/{id}/credit-status?as_of=YYYY-MM-DD&proposed_amount=100.00`
uses today and zero when query values are omitted. All company members may read;
normal master write roles apply to configuration. Response:

```json
{"party_id":"...","as_of":"2026-04-08","credit_limit":"100.00",
 "receivable":"170.00","customer_credit":"10.00","customer_advance":"40.00",
 "current_exposure":"120.00","proposed_amount":"25.00","projected_exposure":"145.00",
 "remaining_credit":"0","exceeded":true,"warning_only":true,"basis":"net_customer_exposure"}
```

Balances come from the same canonical helper as the party statement. Receivable
already includes linked returns, receipts and applications. Only **unused**
customer credits and advances are deducted from that balance. Supplier payables
are never netted. Current exposure is `max(0, receivable - unused credits - unused
advances)`; projected exposure adds the proposed sale **before** clamping to zero.
Remaining credit is clamped to zero; it and the limit are null when disabled.
`exceeded` is strictly greater than the limit, not equal to it. All dates honor
as-of exclusions. This is a business warning, not a journal entry or an automatic
application of an advance/credit.

Clients may show the full proposed amount for a new credit sale, an unposted
sales draft or its conversion. Do not project paid-cash POS or historical
amendments as new credit sales (amendments would require a separate delta policy).
The endpoint is read-only, and exceeding a limit never rejects a posting.

## Recurring reviewed drafts (no automatic posting)

Only `estimate`, `proforma`, `sales_order`, and `purchase_order` sources are
supported. Expenses and posted invoices/bills are not recurring source kinds.
There is no background job, email, external scheduler, journal or stock mutation.
One explicit action creates one ordinary editable nonposting draft.

- `POST /recurring-templates`: `{name,source_record_id,start_date,frequency,
  interval:1,end_date:null,is_active:true}`. Frequency is `weekly` or `monthly`,
  interval is an integer 1–12. The existing reviewed source is copied to a
  server-validated input snapshot; clients cannot submit totals or replacement
  lines. Up to 100 retained templates per company.
- `GET /recurring-templates`: `{templates:[summary]}`.
- `GET /recurring-templates/due?as_of=YYYY-MM-DD`: `{as_of,rows:[summary plus
  overdue_days]}`. India business date (UTC+05:30, independent of server timezone) is default.
  Response also includes `business_date` and `timezone:"Asia/Kolkata"`. Returns only the earliest ungenerated
  occurrence per active template; overdue backlog is generated click-by-click.
- `GET /recurring-templates/{id}`: summary plus `source_record_id` and
  `draft:{kind,name,data}`.
- `PUT /recurring-templates/{id}`: `{version,name,is_active,source_record_id?}`.
  Optional source refresh explicitly changes future snapshot content only and
  must retain the same draft kind. Schedule dates/frequency/interval are immutable;
  pause and create a reviewed replacement template to change cadence.
- `POST /recurring-templates/{id}/occurrences`: `{occurrence_date}`; required
  `Idempotency-Key`. Returns `{template_id,occurrence_date,record,replayed}`.
  Record uses the ordinary fresh detail representation. Date must equal the next
  due date and must not be in the future. All successful writes return 200.

Summary fields: `id,name,version,draft_kind,party_id,party_name,start_date,
frequency,interval,end_date,is_active,next_due,last_generated_date,generated_count`.
Null next_due means the inclusive end date/calendar boundary has been reached.
Monthly dates retain the original anchor day, clamping only individual short
months (31 January → 28/29 February → 31 March). Source due dates are saved as a
0–3650-day offset, not reused as stale absolute dates. Generation recalculates
normal document values and current company branding, never copies posting costs.

All three writes support route-scoped retry keys (optional on template create/
update for compatibility, but clients should always supply them). Replay precedes
version/paused/next-date checks. Different retry keys for the same template/date
return the same existing draft, even after restore or subsequent conversion.
An internal unique occurrence marker backs the company-lock serialization.
Received 409 means a definitive rejected transaction, not an in-progress request;
clients may reload/correct. Timeouts/5xx remain unknown: retain the exact body/key.

Company membership scopes reads; existing owner/editor permissions scope writes.
Archived identities fail closed for new occurrences. Templates are hidden from
normal financial registers and statement transactions but fully retained in
portable backups. Restore validates template/snapshot references, schedule and
complete occurrence history, remapping all record IDs. Generated draft lineage
(`recurring_template_id`, `recurring_occurrence_date`) is server-owned and cannot
be forged by generic creates or draft edits. Existing draft editing/conversion
remains the only path to reviewed posting.
