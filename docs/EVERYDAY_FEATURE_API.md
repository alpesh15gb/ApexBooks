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
