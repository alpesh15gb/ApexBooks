"""Offline evidence audit of an ApexBooks company-data export.

No engine, API client, restore operation, or write handle is constructed. Findings
are review evidence, not correction entries or a statutory-compliance opinion.
"""
import argparse
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from fastapi import HTTPException
from purchase_returns import candidates

ZERO = Decimal(0)
CONTROLS = {'SYS-AR': ('receivable', 1), 'SYS-AP': ('payable', -1),
            'SYS-CUST-CREDIT': ('customer_credit', -1), 'SYS-SUPP-CREDIT': ('supplier_credit', 1),
            'SYS-CUST-ADV': ('customer_advance_net_tax', -1), 'SYS-SUPP-ADV': ('supplier_advance', 1)}
TABLES = ('records', 'accounts', 'journals', 'journal_lines', 'record_postings', 'payment_allocations', 'stock_movements')
LIMITATIONS = [
    'Reads only this supplied snapshot; provenance and completeness outside the file are not verified.',
    'Earlier as-of balances project current surviving records/posting links; amendments/cancellations may prevent reconstruction of the books as they existed then.',
    'Manual/imported control postings and ambiguous legacy allocations need evidence review; a review flag is not proof of misconduct or a prescribed correction.',
    'Automatic journal references are recognized heuristically; a snapshot cannot authenticate their origin.',
    'Provisional-return evidence is checked for presence and linkage, not independently certified as a complete cost-revaluation calculation.',
    'No GST entitlement, filing, supplier evidence, physical stock count, exported PDF status, UI race, or device acceptance is certified.',
    'No historical records, metadata, journals, allocations, locks or production settings are changed.'
]

class AuditInputError(ValueError): pass

def number(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite(): raise ValueError()
        return result
    except (ValueError, InvalidOperation): raise AuditInputError('Invalid or nonfinite accounting number') from None

def day(value):
    try: return date.fromisoformat(value)
    except (TypeError, ValueError): raise AuditInputError('Invalid accounting date') from None

def audit(payload, as_of=None, snapshot_sha256=None):
    if not isinstance(payload, dict) or payload.get('scope') != 'single_company_data_export' or payload.get('schema_version') not in (6, 7, 8):
        raise AuditInputError('Supply an unpacked single_company_data_export JSON, schema 6, 7 or 8')
    tables = {}
    for key in TABLES:
        rows = payload.get(key)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows): raise AuditInputError('Missing or invalid table: ' + key)
        tables[key] = rows
    def index(key):
        result = {}
        for row in tables[key]:
            identity = row.get('id')
            if not isinstance(identity, str) or not identity or identity in result: raise AuditInputError('Missing or duplicate ID in ' + key)
            result[identity] = row
        return result
    records, accounts, journals = index('records'), index('accounts'), index('journals')
    for row in records.values():
        if not isinstance(row.get('data'), dict) or not isinstance(row.get('kind'), str): raise AuditInputError('Invalid record data')
        day(row.get('date')); number(row.get('amount'))
        if 'lines' in row['data'] and (not isinstance(row['data']['lines'], list) or any(not isinstance(line, dict) for line in row['data']['lines'])): raise AuditInputError('Invalid document lines')
        for key in ('advance_tax', 'advance_tax_released'):
            if key in row['data'] and not isinstance(row['data'][key], dict): raise AuditInputError('Invalid tax metadata')
    for row in journals.values(): day(row.get('date'))
    if any(not isinstance(row.get('code'), str) for row in accounts.values()): raise AuditInputError('Invalid account code')
    if not isinstance(payload.get('company'), dict): raise AuditInputError('Missing company metadata')
    cutoff = day(as_of) if as_of else max([day(r['date']) for r in journals.values()] + [day(r['date']) for r in records.values()] + [date.min])
    findings = []; seen = set(); ledger_complete = True
    def flag(code, severity, evidence, action, summary=None):
        signature = (code, json.dumps(evidence, sort_keys=True))
        if signature in seen: return
        seen.add(signature)
        findings.append({'code': code, 'severity': severity, 'summary': summary or code.replace('_', ' ').capitalize(),
                         'evidence': evidence, 'next_action': action})
    posted = set(); linked_journals = set()
    for row in tables['record_postings']:
        if row.get('record_id') not in records or row.get('journal_id') not in journals:
            flag('ORPHAN_POSTING', 'error', row, 'Recover the missing source/link from a verified backup before reconciling.'); ledger_complete = False
        else:
            posted.add(row['record_id']); linked_journals.add(row['journal_id'])
            if records[row['record_id']]['date'] != journals[row['journal_id']]['date']:
                flag('POSTING_DATE_MISMATCH', 'error', row, 'Review the document and journal dates against original evidence.')
    active = [r for r in records.values() if r['id'] in posted and day(r['date']) <= cutoff]
    active_ids = {r['id'] for r in active}
    if as_of and any(day(r['date']) > cutoff for r in journals.values()):
        flag('AS_OF_SNAPSHOT_LIMIT', 'review', {'as_of': cutoff.isoformat()}, 'Use an archived contemporaneous snapshot before concluding a historical-period mismatch.')
    ledger = defaultdict(lambda: ZERO); journal_totals = defaultdict(lambda: ZERO)
    for row in tables['journal_lines']:
        journal, account = journals.get(row.get('journal_id')), accounts.get(row.get('account_id'))
        if not journal or not account:
            flag('ORPHAN_JOURNAL_LINE', 'error', {'journal_id': row.get('journal_id'), 'account_id': row.get('account_id')}, 'Recover the missing account/journal; totals are not complete.'); ledger_complete = False; continue
        debit, credit = number(row.get('debit')), number(row.get('credit'))
        journal_totals[journal['id']] += debit - credit
        if debit < 0 or credit < 0 or (debit > 0) == (credit > 0):
            flag('INVALID_JOURNAL_SIDE', 'error', {'journal_id': journal['id'], 'account_id': account['id']}, 'Review the original posting; do not normalize the export in place.')
        if day(journal['date']) <= cutoff: ledger[account['code']] += debit - credit
        if account.get('code') in CONTROLS and journal['id'] not in linked_journals:
            reference = str(journal.get('reference', ''))
            automatic = reference.startswith(('AUTO:', 'CANCEL:', 'REV:')) and reference.split(':', 1)[1] in records
            if not automatic:
                flag('UNLINKED_PARTY_CONTROL_JOURNAL', 'review', {'journal_id': journal['id'], 'date': journal['date'], 'account': account['code'], 'debit': str(debit), 'credit': str(credit)}, 'Trace manual/imported opening evidence and reconcile the party subledger; do not delete or repost automatically.')
    for jid in journals:
        if jid not in journal_totals: flag('EMPTY_JOURNAL', 'error', {'journal_id': jid}, 'Recover missing journal lines before relying on ledger totals.')
    for jid, value in journal_totals.items():
        if value: flag('UNBALANCED_JOURNAL', 'error', {'journal_id': jid, 'difference': str(value)}, 'Restore or reconcile the original journal with documented approval.')
    allocations_by_payment = defaultdict(lambda: ZERO); allocations_by_document = defaultdict(lambda: ZERO)
    allocations_for_source = defaultdict(list)
    for row in tables['payment_allocations']:
        payment, document = records.get(row.get('payment_id')), records.get(row.get('document_id'))
        amount = number(row.get('amount'))
        if not payment or not document:
            flag('ORPHAN_ALLOCATION', 'error', row, 'Recover missing allocation sources before using ageing totals.'); continue
        allocations_for_source[document['id']].append((payment, amount))
        allocations_by_payment[payment['id']] += amount
        if day(payment['date']) <= cutoff: allocations_by_document[document['id']] += amount
        if amount <= 0 or payment['id'] not in posted or document['id'] not in posted:
            flag('INACTIVE_OR_INVALID_ALLOCATION', 'error', row, 'Review cancellation/amendment history and surviving allocation rows.')
        if str(payment.get('name', '')).strip().casefold() != str(document.get('name', '')).strip().casefold():
            flag('CROSS_PARTY_ALLOCATION', 'error', row, 'Verify the intended party and settlement source.')
    party = defaultdict(lambda: defaultdict(lambda: ZERO)); expected = defaultdict(lambda: ZERO); ageing = defaultdict(lambda: ZERO)
    for row in active:
        rid, kind, data, amount = row['id'], row['kind'], row['data'], number(row['amount'])
        name = str(row.get('name', '')).strip().casefold()
        if kind in ('payment_in', 'payment_out') and 'unallocated_credit' in data:
            flag('PAYMENT_DERIVED_CREDIT_METADATA', 'error' if number(data['unallocated_credit']) else 'review', {'record_id': rid, 'value': str(data['unallocated_credit'])}, 'Compare GL, allocations and the affected historical party report; the field belongs to note credits, not payments.')
        allowed_event = kind in ('advance_application', 'advance_refund') or kind == 'payment_in' and data.get('is_advance') is True
        if data.get('advance_tax_event') and not allowed_event:
            flag('MISCLASSIFIED_ADVANCE_TAX_EVENT', 'error', {'record_id': rid, 'kind': kind}, 'Reconcile invoice/HSN and advance schedules before any GST filing correction.')
        if data.get('advance_tax') and kind not in ('payment_in', 'payment_out'):
            flag('UNEXPECTED_DERIVED_ADVANCE_METADATA', 'review', {'record_id': rid, 'kind': kind}, 'Verify server/import provenance and affected tax schedules.')
        if data.get('cancelled'):
            flag('CANCELLED_RECORD_STILL_POSTED', 'error', {'record_id': rid}, 'Review the retained posting and cancellation evidence.')
        if kind in ('credit_note', 'debit_note'):
            unallocated = number(data.get('unallocated_credit', 0))
            derived = amount - allocations_by_payment[rid]
            if unallocated != derived:
                flag('NOTE_CREDIT_ALLOCATION_MISMATCH', 'error', {'record_id': rid, 'stored_credit': str(unallocated), 'amount_less_allocations': str(derived)}, 'Reconcile the note’s original allocation and refundable credit; preserve subsequent settlements.')
            key = 'customer_credit' if kind == 'credit_note' else 'supplier_credit'
            used = sum((number(r['amount']) for r in active if r['kind'] in ('credit_application','customer_refund','supplier_refund') and r['data'].get('credit_note_id') == rid), ZERO)
            expected[key] += unallocated - used
            source = records.get(data.get('applied_to'))
            if source:
                future = [r['id'] for r, value in allocations_for_source[source['id']] if r['id'] != rid and day(r['date']) > day(row['date'])]
                if future and unallocated > 0:
                    flag('BACKDATED_NOTE_WITH_LATER_SETTLEMENT', 'review', {'record_id': rid, 'source_id': source['id'], 'later_settlement_ids': sorted(future), 'credit': str(unallocated)}, 'Reproduce the period between note and settlement dates; current ending balances alone cannot validate that period.')
        if kind in ('payment_in', 'payment_out') and data.get('is_advance'):
            settlements = [r for r in active if r['kind'] in ('advance_application','advance_refund') and r['data'].get('advance_id') == rid]
            used = sum((number(r['amount']) for r in settlements), ZERO)
            remaining_tax = sum((number(v) for v in data.get('advance_tax', {}).values()), ZERO) - sum((number(v) for r in settlements for v in r['data'].get('advance_tax_released', {}).values()), ZERO)
            expected['customer_advance_net_tax' if kind == 'payment_in' else 'supplier_advance'] += amount - used - (remaining_tax if kind == 'payment_in' else ZERO)
            continue
        effect = {}
        if kind in ('sales_invoice','opening_receivable'): effect['receivable'] = amount
        elif kind in ('purchase_bill','opening_payable'): effect['payable'] = amount
        elif kind in ('payment_in','credit_note'): effect['receivable'] = -amount + (number(data.get('unallocated_credit',0)) if kind == 'credit_note' else ZERO)
        elif kind in ('payment_out','debit_note'): effect['payable'] = -amount + (number(data.get('unallocated_credit',0)) if kind == 'debit_note' else ZERO)
        elif kind in ('advance_application','credit_application'): effect['receivable' if data.get('payment_kind') == 'payment_in' else 'payable'] = -amount
        for side, value in effect.items(): expected[side] += value; party[name][side] += value
        if kind in ('sales_invoice','opening_receivable','purchase_bill','opening_payable'):
            side = 'receivable' if kind in ('sales_invoice','opening_receivable') else 'payable'
            remaining = amount - allocations_by_document[rid]
            if remaining < 0: flag('DOCUMENT_OVERALLOCATED', 'error', {'record_id': rid, 'excess': str(-remaining)}, 'Review all linked settlements and their dates atomically.')
            ageing[side] += max(remaining, ZERO); party[name]['ageing_' + side] += max(remaining, ZERO)
        if allocations_by_payment[rid] > amount:
            flag('PAYMENT_OVERALLOCATED', 'error', {'record_id': rid, 'excess': str(allocations_by_payment[rid] - amount)}, 'Review all allocation rows against this payment/note.')
    comparisons = []
    for code, (side, sign) in CONTROLS.items():
        gl = ledger[code] * sign; subledger = expected[side]
        comparisons.append({'account': code, 'ledger': str(gl), 'subledger': str(subledger), 'difference': str(gl - subledger), 'complete': ledger_complete})
        if ledger_complete and gl != subledger: flag('CONTROL_SUBLEDGER_MISMATCH', 'error', comparisons[-1], 'Trace control journal lines, source metadata and dated allocations; approve an evidence-backed correction separately.')
    for name, values in party.items():
        for side in ('receivable','payable'):
            if values[side] != values['ageing_' + side]:
                flag('PARTY_AGEING_MISMATCH', 'error', {'party': name, 'side': side, 'statement': str(values[side]), 'ageing': str(values['ageing_' + side])}, 'Compare the party’s documents and allocation dates at this cutoff.')
    # Source-linked purchase returns: references, treatment and per-source caps.
    notes_by_source = defaultdict(list)
    for row in active:
        if row['kind'] == 'debit_note': notes_by_source[row['data'].get('applied_to')].append(row)
    for sid, notes in notes_by_source.items():
        source = records.get(sid)
        if not source or source['kind'] != 'purchase_bill':
            flag('RETURN_SOURCE_MISSING', 'error', {'source_id': sid, 'note_ids': [n['id'] for n in notes]}, 'Recover the original supplier bill and its source-line evidence.'); continue
        if sid not in posted:
            flag('RETURN_SOURCE_NOT_POSTED', 'error', {'source_id': sid}, 'Review source cancellation and retained return postings.')
        totals = defaultdict(lambda: defaultdict(lambda: ZERO))
        for note in notes:
            for index, line in enumerate(note['data'].get('lines', [])):
                evidence = {'record_id': note['id'], 'line_index': index, 'source_id': sid}
                try: matched = candidates(line, SimpleNamespace(**source))
                except (HTTPException, ValueError, ArithmeticError, TypeError, KeyError):
                    flag('RETURN_REFERENCE_INVALID', 'error', evidence, 'Verify original IDs/fingerprints, including any restore remapping; do not regenerate a token blindly.'); continue
                originals = [source['data']['lines'][i] for i in matched]
                treatments = {r.get('itc_treatment') for r in originals}
                if len(matched) != 1:
                    flag('RETURN_SOURCE_AMBIGUOUS', 'review', {**evidence, 'candidate_lines': matched}, 'Identify the original line using supplier evidence before allocating further returns.')
                if len(treatments) == 1 and None not in treatments and line.get('itc_treatment') not in treatments:
                    flag('RETURN_ITC_MISMATCH', 'error', {**evidence, 'source_treatment': next(iter(treatments)), 'return_treatment': line.get('itc_treatment')}, 'Reconcile input-tax and purchase/inventory postings against the original bill treatment.')
                elif len(treatments) != 1 or None in treatments:
                    flag('RETURN_ITC_UNVERIFIED', 'review', evidence, 'Obtain line-specific ITC treatment evidence; no entitlement is inferred.')
                for field in ('quantity','taxable','tax'):
                    try:
                        if field not in line or number(line[field]) < 0: raise AuditInputError('missing/negative')
                        totals[tuple(matched)][field] += number(line[field])
                    except AuditInputError: flag('RETURN_LINE_VALUE_UNVERIFIED', 'review', {**evidence, 'field': field}, 'Recover the missing line value before calculating remaining capacity.')
        groups = list(totals)
        if any(set(a) & set(b) for i, a in enumerate(groups) for b in groups[i + 1:]):
            flag('RETURN_POOL_OVERLAP', 'review', {'source_id': sid, 'groups': [list(g) for g in groups]}, 'Resolve overlapping pooled and explicit return lines before assessing cumulative line caps.')
        for indexes, values in totals.items():
            for field, used in values.items():
                try: cap = sum((number(source['data']['lines'][i][field]) for i in indexes), ZERO)
                except (KeyError, AuditInputError): continue
                if used > cap: flag('RETURN_LINE_CAP_EXCEEDED', 'error', {'source_id': sid, 'source_lines': list(indexes), 'field': field, 'used': str(used), 'source': str(cap)}, 'Reconcile cumulative partial notes, including duplicate source selections.')
        for field in ('cgst','sgst','igst','supplier_tax','pending_input_cgst','pending_input_sgst','pending_input_igst','input_tax_ineligible'):
            used = sum((number(n['data'].get(field, 0)) for n in notes), ZERO); cap = number(source['data'].get(field, 0))
            if used > cap: flag('RETURN_TAX_COMPONENT_EXCESS', 'error', {'source_id': sid, 'component': field, 'returned': str(used), 'source': str(cap)}, 'Review ITC inheritance and partial-return tax rounding; do not move excess between tax components without evidence.')
    stock = defaultdict(lambda: [ZERO, ZERO]); stock_complete = True; stock_days = defaultdict(set); movements_by_item = defaultdict(list)
    for movement in tables['stock_movements']:
        source = records.get(movement.get('source_record_id'))
        if not source:
            flag('ORPHAN_STOCK_MOVEMENT', 'error', {'movement_id': movement.get('id')}, 'Recover the source document before valuing this stock.'); stock_complete = False; continue
        if day(movement['date']) > cutoff: continue
        item = movement['item_id']; qty = number(movement['quantity']); stock[item][0] += qty
        if movement.get('cost_value') is None:
            flag('UNVALUED_STOCK_MOVEMENT', 'review', {'movement_id': movement.get('id'), 'item_id': item}, 'Verify historical valuation before relying on inventory totals.'); stock_complete = False
        else: stock[item][1] += number(movement['cost_value'])
        movements_by_item[item].append(movement)
        if source['kind'] != 'stock_opening': stock_days[(item, movement['date'])].add(source['id'])
        if source['kind'] in ('credit_note','stock_return'):
            original = records.get(source['data'].get('applied_to'))
            provisional = original and any(l.get('item_id') == item and (l.get('stock_cost_provisional') or number(l.get('shortage_quantity',0)) > 0) for l in original['data'].get('lines',[]))
            lines = source['data'].get('lines', []); index = movement.get('line_index', -1)
            line = lines[index] if isinstance(index,int) and 0 <= index < len(lines) else {}
            evidence = line.get('return_cost_reconciliation')
            if provisional and not evidence:
                flag('PROVISIONAL_RETURN_UNRECONCILED', 'error', {'record_id': source['id'], 'source_id': original['id'], 'item_id': item, 'recorded_cost': movement.get('cost_value')}, 'Replay shortages and replenishments on an isolated copy, quantify inventory/purchase/COGS differences, and approve corrections separately.')
            if evidence:
                if not isinstance(evidence,dict) or not isinstance(evidence.get('receipts'),list) or any(not isinstance(r, dict) or r.get('record_id') not in records for r in evidence.get('receipts', [])):
                    flag('RECONCILIATION_EVIDENCE_INVALID', 'review', {'record_id': source['id'], 'item_id': item}, 'Recover the referenced replenishment evidence; metadata presence alone is not valuation proof.')
    ambiguous_items = set()
    for (item, issued), ids in stock_days.items():
        stamps = [records[rid]['data'].get('created_at') for rid in ids]
        if len(ids) > 1 and (not all(stamps) or len(set(stamps)) != len(stamps)):
            ambiguous_items.add(item); flag('STOCK_ORDER_AMBIGUOUS', 'review', {'item_id': item, 'date': issued, 'record_ids': sorted(ids)}, 'Recover transaction order from source evidence before replaying provisional costing.')
    provisional_sources = []
    for item, movements in movements_by_item.items():
        for movement in movements:
            row = records[movement['source_record_id']]
            if row['kind'] in ('sales_invoice','pos') and any(l.get('item_id') == item and l.get('stock_cost_provisional') for l in row['data'].get('lines',[])):
                entry = {'record_id': row['id'], 'item_id': item, 'ordering_reliable': item not in ambiguous_items}
                if entry not in provisional_sources: provisional_sources.append(entry)
    for item, (qty, value) in stock.items():
        if qty == 0 and value != 0 or qty < 0 and value > 0:
            flag('STOCK_QUANTITY_VALUE_INCONSISTENT', 'error', {'item_id': item, 'quantity': str(qty), 'value': str(value)}, 'Reconcile negative-stock replenishments and returns before writing any adjustment.')
    stock_value = sum((v[1] for v in stock.values()), ZERO)
    if stock_complete and ledger_complete and stock_value != ledger['SYS-INVENTORY']:
        flag('INVENTORY_CONTROL_MISMATCH', 'error', {'ledger': str(ledger['SYS-INVENTORY']), 'movements': str(stock_value)}, 'Trace inventory-control journals and source stock movements on the same snapshot.')
    return {'audit_version': 1, 'mutates_books': False, 'snapshot_sha256': snapshot_sha256,
            'company_id': payload.get('company', {}).get('id'), 'exported_at': payload.get('exported_at'), 'as_of': cutoff.isoformat(),
            'counts': {key: len(rows) for key, rows in tables.items()}, 'control_comparisons': comparisons,
            'ageing_totals': {k: str(v) for k,v in ageing.items()}, 'provisional_sources': provisional_sources,
            'findings': sorted(findings, key=lambda f: (f['severity'], f['code'], json.dumps(f['evidence'],sort_keys=True))),
            'limitations': LIMITATIONS, 'status': 'findings' if findings else 'no_findings_in_implemented_checks'}


def load_snapshot(path):
    with Path(path).open('rb') as handle: raw = handle.read(128 * 1024 * 1024 + 1)
    if len(raw) > 128 * 1024 * 1024: raise AuditInputError('Export exceeds the 128 MiB audit input limit')
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result: raise AuditInputError('Duplicate JSON key')
            result[key] = value
        return result
    def invalid(value): raise AuditInputError('Nonfinite JSON constant')
    try: payload = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, UnicodeError, RecursionError) as error: raise AuditInputError('Invalid JSON export: ' + str(error)) from None
    return payload, hashlib.sha256(raw).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export_json'); parser.add_argument('--as-of', help='YYYY-MM-DD; historical projection limitations apply')
    args = parser.parse_args(argv)
    try:
        payload, digest = load_snapshot(args.export_json); report = audit(payload, args.as_of, digest)
    except (AuditInputError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'status':'invalid_input','mutates_books':False,'error':str(error)})); return 2
    print(json.dumps(report, indent=2, sort_keys=True)); return 1 if report['findings'] else 0

if __name__ == '__main__': sys.exit(main())
