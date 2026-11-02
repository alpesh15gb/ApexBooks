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
