"""Source-only migration audit. A classified row is never a posted ledger entry.

Codes 1, 2, 3, 27 and 28 were checked against the supplied Apex Integrations
backup and its native Vyapar All Transactions export. Unknown codes stay blocked.
"""
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP

TYPE_MAP = {1: ('Sale', 'sales_invoice'), 2: ('Purchase', 'purchase_bill'),
            3: ('Payment-In', 'payment_in'), 27: ('Estimate', 'estimate'),
            28: ('Purchase Order', 'purchase_order')}

def decimal(value):
    result = Decimal(str(value or 0))
    if not result.is_finite(): raise ValueError('Non-finite source amount')
    return result

def rounded(value): return decimal(value).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

def transaction_audit(tables):
    transactions = {row['txn_id']: row for row in tables.get('kb_transactions', [])}
    parties = {row['name_id']: row for row in tables.get('kb_names', [])}
    items = {row['item_id']: row for row in tables.get('kb_items', [])}
    banks = {row['paymentType_id']: row for row in tables.get('kb_paymentTypes', [])}
    prefixes = {row['prefix_id']: row.get('prefix_value') or '' for row in tables.get('kb_prefix', [])}
    lines, payments, applied, conversions = defaultdict(list), defaultdict(list), defaultdict(Decimal), defaultdict(list)
    global_issues = []
    for line in tables.get('kb_lineitems', []):
        lines[line['lineitem_txn_id']].append(line)
        if line['lineitem_txn_id'] not in transactions: global_issues.append('Orphan line: ' + str(line.get('lineitem_id')))
    for payment in tables.get('txn_payment_mapping', []):
        payments[payment['txn_id']].append(payment)
        if payment['txn_id'] not in transactions: global_issues.append('Orphan payment mapping: ' + str(payment.get('id')))
    links = []
    for link in tables.get('kb_txn_links', []):
        first, second = transactions.get(link.get('txn_links_txn_1_id')), transactions.get(link.get('txn_links_txn_2_id'))
        issue = ''
        if not first or not second: issue = 'Missing linked transaction'
        elif first.get('txn_type') != 1 or second.get('txn_type') != 3: issue = 'Unsupported payment link types'
        elif first.get('txn_name_id') != second.get('txn_name_id'): issue = 'Linked party mismatch'
        elif str(second.get('txn_date',''))[:10] < str(first.get('txn_date',''))[:10]: issue = 'Receipt predates invoice'
        amount = decimal(link.get('txn_links_amount'))
        if amount <= 0: issue = 'Invalid allocation amount'
        if not issue:
            applied[first['txn_id']] += amount
            applied[second['txn_id']] += amount
        else: global_issues.append('Payment link ' + str(link.get('txn_links_id')) + ': ' + issue)
        links.append({'invoice_id':link.get('txn_links_txn_1_id'), 'payment_id':link.get('txn_links_txn_2_id'), 'amount':str(rounded(amount)), 'issue':issue})
    for link in tables.get('kb_linked_transactions', []):
        conversions[link['txn_source_id']].append(link['txn_destination_id'])
        if link['txn_source_id'] not in transactions or link['txn_destination_id'] not in transactions:
            global_issues.append('Orphan conversion link: ' + str(link.get('linked_id')))
    rows=[]
    for source_id, row in sorted(transactions.items()):
        code=row.get('txn_type'); label, kind=TYPE_MAP.get(code, ('Unknown','unsupported'))
        issues=[]
        if kind=='unsupported': issues.append('Unknown transaction type')
        expected_statuses={1:{1},2:{1},3:{1},27:{2,4},28:{2}}
        if code in expected_statuses and row.get('txn_status') not in expected_statuses[code]: issues.append('Unverified source status')
        party=parties.get(row.get('txn_name_id'))
        if not party: issues.append('Missing party')
        cash=decimal(row.get('txn_cash_amount')); balance=decimal(row.get('txn_balance_amount'))
        amount=cash+balance
        source_lines=lines[source_id]
        line_total=sum((decimal(line.get('total_amount')) for line in source_lines),Decimal(0))
        line_tax=sum((decimal(line.get('lineitem_tax_amount')) for line in source_lines),Decimal(0))
        charges=sum((decimal(row.get('txn_ac'+str(i)+'_amount')) for i in (1,2,3)),Decimal(0))
        round_off=decimal(row.get('txn_round_off_amount'))
        if code in {1,2,27,28}:
            if not source_lines: issues.append('Missing document lines')
            if abs(rounded(line_total+charges+round_off)-rounded(amount)) > Decimal('.01'): issues.append('Line totals and document amount do not reconcile')
        for line in source_lines:
            if line.get('item_id') not in items: issues.append('Missing linked item')
        mapped_cash=sum((decimal(p.get('amount')) for p in payments[source_id]),Decimal(0))
        if abs(rounded(mapped_cash)-rounded(cash)) > Decimal('.01'): issues.append('Payment mapping does not reconcile')
        if any(p.get('payment_id') not in banks for p in payments[source_id]): issues.append('Missing payment account')
        converted=code==27 and row.get('txn_status')==4
        destinations=conversions[source_id]
        if converted and not destinations: issues.append('Converted estimate has no destination link')
        if converted and any(transactions.get(i,{}).get('txn_type')!=1 for i in destinations): issues.append('Unexpected conversion destination type')
        if applied[source_id] > (balance if code==1 else cash) + Decimal('.01'): issues.append('Allocations exceed source amount')
        prefix=row.get('txn_invoice_prefix') or prefixes.get(row.get('txn_prefix_id'),'')
        ref=str(row.get('txn_ref_number_char') or '')
        reference=prefix+ref if prefix and not ref.startswith(prefix) else ref
        rows.append({'source_id':source_id,'source_type':code,'source_type_name':label,'apex_kind':kind,
            'date':str(row.get('txn_date') or '')[:10], 'reference':reference,'party':party.get('full_name','') if party else '',
            'source_status':row.get('txn_status'),'converted':converted,'conversion_destinations':destinations,
            'amount':str(rounded(amount)),'paid_at_document':str(rounded(cash)), 'line_tax':str(rounded(line_tax)),
            'header_tax':str(rounded(row.get('txn_tax_amount'))), 'additional_charges':str(rounded(charges)),
            'round_off_raw':str(round_off),'payment_mapping_total':str(rounded(mapped_cash)),
            'linked_amount':str(rounded(applied[source_id])),
            'derived_invoice_outstanding':str(rounded(balance-applied[source_id])) if code==1 else None,
            'line_count':len(source_lines),'source_tax_inclusive_code':row.get('txn_tax_inclusive'),
            'source_classification':'review_required' if issues else 'classified',
            'live_ledger_status':'not_posted_by_this_source_audit','issues':list(dict.fromkeys(issues))})
    def total(predicate,key='amount'): return str(sum((decimal(r[key]) for r in rows if predicate(r)),Decimal(0)))
    return {'scope':'source_mapping_audit_only','live_transactions_posted':0,'rows':rows,'payment_links':links,
        'global_issues':global_issues,'type_counts':dict(Counter(str(r['source_type']) for r in rows)),
        'totals':{'sales':total(lambda r:r['source_type']==1), 'purchases':total(lambda r:r['source_type']==2),
            'receipts':total(lambda r:r['source_type']==3), 'receivable':total(lambda r:r['source_type']==1,'derived_invoice_outstanding'),
            'active_estimates':total(lambda r:r['source_type']==27 and not r['converted']),
            'purchase_orders':total(lambda r:r['source_type']==28)},
        'source_classified_count':sum(r['source_classification']=='classified' for r in rows),
        'review_required_count':sum(bool(r['issues']) for r in rows),
        'missing_archive_tables':[name for name in ('kb_linked_transactions','kb_prefix','kb_item_units_mapping') if name not in tables]}
