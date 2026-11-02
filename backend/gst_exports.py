"""Distinct GST preparation exports. Never invent portal filing/claim/payment data.

GSTR-1 sheet headers are pinned to GSTN's downloaded V2.2 workbook. JSON is
an unsigned preparation file for review in the current GST offline utility.
GSTR-2A is supplier-generated: our inward workbook is explicitly book-derived.
"""
import calendar
import json
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer

SCHEMA = json.loads(Path(__file__).with_name('gst_export_schema.json').read_text(encoding='utf-8'))
HEADS = ('igst', 'cgst', 'sgst')
ZERO = Decimal('0')
CENT = Decimal('.01')
POS = {s.split('-')[0]: s for s in SCHEMA['master']['POS']}
UQC = {s.split('-')[0]: s for s in SCHEMA['master']['UQC']}
NOTE = 'BOOK-DERIVED DRAFT. Not filed. Verify against GST portal records and GSTR-2B before filing or claiming ITC.'


def dec(value):
    return Decimal(str(value or 0))


def rounded(value):
    return dec(value).quantize(CENT, rounding=ROUND_HALF_UP)


def number(value):
    return float(rounded(value))


def gstin_valid(value):
    if not re.fullmatch(r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]', value):
        return False
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    total = 0
    for i, char in enumerate(reversed(value[:-1])):
        product = alphabet.index(char) * (2 if i % 2 == 0 else 1)
        total += product // 36 + product % 36
    return value[-1] == alphabet[(36 - total % 36) % 36]


def full_period(start, end):
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    months = (b.year - a.year) * 12 + b.month - a.month + 1
    return a.day == 1 and b.day == calendar.monthrange(b.year, b.month)[1] and (
        months == 1 or months == 3 and a.month in (1, 4, 7, 10))


def sheet(name, title, headers, rows, money_columns=()):
    return {'name': name, 'title': title, 'headers': headers, 'rows': rows,
            'money_columns': list(money_columns)}


def document_lines(record):
    """Allocate existing posted tax heads cumulatively, preserving paise totals."""
    data = record['data']
    lines = data.get('lines', [])
    total_tax = sum((dec(line.get('tax')) for line in lines), ZERO)
    cumulative = ZERO
    used = {h: ZERO for h in HEADS}
    result = []
    for line in lines:
        cumulative += dec(line.get('tax'))
        taxes = {}
        for h in HEADS:
            target = rounded(dec(data.get(h)) * cumulative / total_tax) if total_tax else ZERO
            taxes[h] = target - used[h]
            used[h] = target
        result.append({**line, **taxes})
    return result


def prepare(kind, data, company, records):
    issues = []
    warnings = []

    def issue(record, message):
        item = {'document': record.get('number', 'Company / period'), 'message': message}
        if item not in issues:
            issues.append(item)

    if not data['applicable']:
        issue({}, 'GST returns require the regular GST tax profile.')
    if not gstin_valid(company.gstin or '') or (company.gstin or '')[:2] != company.state_code:
        issue({}, 'Enter a valid company GSTIN, including its check digit and state code.')
    if kind == 'gstr1' and not full_period(data['from_date'], data['to_date']):
        issue({}, 'Select a complete calendar month or financial quarter for GSTR-1 preparation JSON.')
    if kind == 'gstr1':
        sheets, payload = outward_sheets(records, company, issue, data)
        warnings += ['Review cancelled documents, prior-period amendments, exports/SEZ, e-commerce and special supplies separately; the app does not capture their complete filing details.',
                     'JSON and XLSX are preparation files. Validate and complete them in the current GST Returns Offline Tool before upload.']
    elif kind == 'gstr2a':
        sheets = inward_sheets(records, company)
        payload = None
        warnings += ['This is a purchase-book reconciliation workbook, not the supplier-filed portal GSTR-2A.',
                     'Supplier return period/status, amendments, ISD, TDS/TCS and import/SEZ details cannot be inferred from entered purchase bills.']
    else:
        sheets = summary_sheets(records, data, company)
        payload = None
        warnings += ['Blank cells mean not captured or not verified, not nil liability.',
                     'ITC is provisional. Imports, ISD, RCM, reversals, special supplies, interest, late fees and actual payments require portal/other records.']
    info = {'kind': kind, 'template': SCHEMA['template'] if kind == 'gstr1' else None,
            'source': SCHEMA['source'], 'checked_on': SCHEMA['checked_on'],
            'json_available': kind == 'gstr1' and not issues,
            'issues': issues, 'warnings': warnings,
            'schedules': [{'name': s['name'], 'title': s['title'], 'rows': len(s['rows'])} for s in sheets]}
    return {'info': info, 'sheets': sheets, 'payload': payload,
            'company': {'name': company.name, 'gstin': company.gstin or ''},
            'from_date': data['from_date'], 'to_date': data['to_date']}


def outward_sheets(records, company, issue, report):
    schema_sheets = {k: v for k, v in SCHEMA['sheets'].items() if v['headers']}
    rows = {k: [] for k in schema_sheets}
    b2b, b2cl, cdnr, cdnur = defaultdict(list), defaultdict(list), defaultdict(list), []
    small, exempt, advances, hsn = {}, {}, {}, {}
    documents = defaultdict(list)
    seen_numbers = set()
    for r in records:
        d = r['data']
        if r['kind'] not in {'sales_invoice', 'pos', 'credit_note'} and not d.get('advance_tax_event'):
            continue
        parent = r.get('parent') or {}
        parent_data = parent.get('data', {})
        advance = bool(d.get('advance_tax_event'))
        gstin = str(d.get('party_gstin') or (parent_data.get('party_gstin') if r['kind'] == 'credit_note' else '') or '').upper()
        place = str(d.get('place_of_supply') or (parent_data.get('place_of_supply') if advance else '') or '')
        inter = place != company.state_code
        sign = Decimal('-1') if r['kind'] == 'credit_note' else Decimal('1')
        if place not in POS:
            issue(r, 'Select a valid place of supply.')
        if gstin and not gstin_valid(gstin):
            issue(r, 'Recipient GSTIN has an invalid format or check digit.')
        if not re.fullmatch(r'[A-Za-z0-9/-]{1,16}', r['number']):
            issue(r, 'Document number must have 1–16 letters/digits, slash or hyphen.')
        if (r['kind'], r['number']) in seen_numbers:
            issue(r, 'Duplicate document number in this period.')
        seen_numbers.add((r['kind'], r['number']))
        if any(d.get(k) for k in ('reverse_charge', 'export_type', 'ecommerce_gstin', 'ecommerce_operator_gstin', 'sez', 'cess')):
            issue(r, 'Special supply, reverse charge, e-commerce or cess needs a separately reviewed filing classification.')
        lines = document_lines(r)
        if abs(sum((dec(l.get('tax')) for l in lines), ZERO) - sum((dec(d.get(h)) for h in HEADS), ZERO)) > CENT:
            issue(r, 'Posted line tax does not reconcile with document tax heads.')
        if advance:
            target = 'at' if dec(d.get('taxable')) >= 0 else 'atadj'
            rate = dec(d.get('advance_gst_rate') or parent_data.get('advance_gst_rate') or (lines[0].get('gst_rate') if lines else 0))
            key = (target, place, rate)
            a = advances.setdefault(key, {'base': ZERO, **{h: ZERO for h in HEADS}})
            a['base'] += abs(dec(d.get('taxable')))
            for head in HEADS: a[head] += abs(dec(d.get(head)))
            if r['kind'] == 'advance_refund':
                issue(r, 'Refunded service advance needs review against the original tax-period adjustment.')
            if r['kind'] in {'payment_in', 'advance_refund'}:
                documents[6 if target == 'at' else 8].append(r['number'])
            continue
        documents[5 if r['kind'] == 'credit_note' else 1].append(r['number'])
        original_amount = dec(parent.get('amount', r['amount']))
        original_date = date.fromisoformat(parent.get('date', r['date']))
        threshold = Decimal('100000') if original_date >= date(2024, 8, 1) else Decimal('250000')
        large = not gstin and inter and original_amount > threshold
        grouped = {}
        for line in lines:
            rate = dec(line.get('gst_rate'))
            base = dec(line.get('taxable'))
            treatment = line.get('tax_treatment', 'taxable')
            code = str(line.get('hsn', ''))
            raw_unit = str(line.get('unit', '')).upper().strip().split('-')[0]
            raw_unit = {'KG': 'KGS', 'PC': 'PCS', 'PIECE': 'PCS', 'PIECES': 'PCS', 'L': 'LTR'}.get(raw_unit, raw_unit)
            unit = 'NA' if code.startswith('99') else raw_unit
            if not re.fullmatch(r'\d{4}|\d{6}|\d{8}', code):
                issue(r, 'Enter a valid 4, 6 or 8 digit HSN/SAC for every line; confirm the AATO digit requirement.')
            if unit != 'NA' and unit not in UQC:
                issue(r, 'Map the item unit to a GST UQC before generating JSON.')
                unit = 'OTH'
            if rate not in [dec(v) for v in SCHEMA['master']['Tax Rate']]:
                issue(r, 'GST rate is not in the current offline template rate list.')
            key = ('hsn(b2b)' if gstin else 'hsn(b2c)', code, unit, rate)
            h = hsn.setdefault(key, {'description': str(line.get('description', '')), 'qty': ZERO, 'base': ZERO, 'total': ZERO, **{k: ZERO for k in HEADS}})
            h['qty'] += sign * (ZERO if unit == 'NA' else dec(line.get('quantity')))
            h['base'] += sign * base
            h['total'] += sign * (base + dec(line.get('tax')))
            for head in HEADS:
                h[head] += sign * dec(line.get(head))
            if treatment in {'nil_rated', 'exempt', 'non_gst'}:
                key = ('Inter-State' if inter else 'Intra-State') + ' supplies to ' + ('registered' if gstin else 'unregistered') + ' persons'
                e = exempt.setdefault(key, {k: ZERO for k in ('nil_rated', 'exempt', 'non_gst')})
                e[treatment] += sign * base
                continue
            g = grouped.setdefault(rate, {'txval': ZERO, **{h: ZERO for h in HEADS}})
            g['txval'] += base
            for head in HEADS:
                g[head] += dec(line.get(head))
        items = []
        for index, (rate, g) in enumerate(sorted(grouped.items()), 1):
            det = {'rt': number(rate), 'txval': number(g['txval']), 'iamt': number(g['igst']), 'camt': number(g['cgst']), 'samt': number(g['sgst']), 'csamt': 0}
            items.append({'num': index, 'itm_det': det})
            if r['kind'] == 'credit_note' and gstin:
                rows['cdnr'].append([gstin, r['party'], r['number'], datetime.fromisoformat(r['date']), 'C', POS.get(place, place), 'N', 'Regular B2B', number(r['amount']), None, number(rate), number(g['txval']), 0])
            elif r['kind'] == 'credit_note' and large:
                rows['cdnur'].append(['B2CL', r['number'], datetime.fromisoformat(r['date']), 'C', POS.get(place, place), number(r['amount']), None, number(rate), number(g['txval']), 0])
            elif gstin:
                rows['b2b,sez,de'].append([gstin, r['party'], r['number'], datetime.fromisoformat(r['date']), number(r['amount']), POS.get(place, place), 'N', None, 'Regular B2B', None, number(rate), number(g['txval']), 0])
            elif large:
                rows['b2cl'].append([r['number'], datetime.fromisoformat(r['date']), number(r['amount']), POS.get(place, place), None, number(rate), number(g['txval']), 0, None])
            else:
                key = (place, rate)
                s = small.setdefault(key, {'txval': ZERO, **{h: ZERO for h in HEADS}})
                for field in s:
                    s[field] += sign * g[field]
        if not items:
            continue
        common = {'val': number(r['amount']), 'pos': place, 'rchrg': 'N', 'inv_typ': 'R', 'itms': items}
        if r['kind'] == 'credit_note':
            note = {**common, 'nt_num': r['number'], 'nt_dt': date.fromisoformat(r['date']).strftime('%d-%m-%Y'), 'ntty': 'C'}
            if gstin:
                cdnr[gstin].append(note)
            elif large:
                note.pop('rchrg'); note.pop('inv_typ'); note['typ'] = 'B2CL'
                cdnur.append(note)
        else:
            inv = {**common, 'inum': r['number'], 'idt': date.fromisoformat(r['date']).strftime('%d-%m-%Y')}
            if gstin:
                b2b[gstin].append(inv)
            elif large:
                inv.pop('pos'); inv.pop('rchrg'); inv.pop('inv_typ')
                b2cl[place].append(inv)
    payload = {'gstin': company.gstin or '', 'fp': date.fromisoformat(report['to_date']).strftime('%m%Y')}
    if b2b: payload['b2b'] = [{'ctin': k, 'inv': v} for k, v in sorted(b2b.items())]
    if b2cl: payload['b2cl'] = [{'pos': k, 'inv': v} for k, v in sorted(b2cl.items())]
    if cdnr: payload['cdnr'] = [{'ctin': k, 'nt': v} for k, v in sorted(cdnr.items())]
    if cdnur: payload['cdnur'] = cdnur
    for (place, rate), g in sorted(small.items()):
        rows['b2cs'].append(['OE', POS.get(place, place), None, number(rate), number(g['txval']), 0, None])
        payload.setdefault('b2cs', []).append({'sply_ty': 'INTRA' if place == company.state_code else 'INTER', 'typ': 'OE', 'pos': place, 'rt': number(rate), 'txval': number(g['txval']), 'iamt': number(g['igst']), 'camt': number(g['cgst']), 'samt': number(g['sgst']), 'csamt': 0})
    for desc, e in sorted(exempt.items()):
        rows['exemp'].append([desc, number(e['nil_rated']), number(e['exempt']), number(e['non_gst'])])
        typ = ('INTR' if desc.startswith('Inter-State') else 'INTRA') + ('B2B' if 'to registered' in desc else 'B2C')
        payload.setdefault('nil', {'inv': []})['inv'].append({'sply_ty': typ, 'nil_amt': number(e['nil_rated']), 'expt_amt': number(e['exempt']), 'ngsup_amt': number(e['non_gst'])})
    for (target, place, rate), a in sorted(advances.items()):
        rows[target].append([POS.get(place, place), None, number(rate), number(a['base']), 0])
        # GSTN groups advance slabs by place of supply.
        group = next((v for v in payload.setdefault(target, []) if v['pos'] == place), None)
        if group is None:
            group = {'pos': place, 'sply_ty': 'INTRA' if place == company.state_code else 'INTER', 'itms': []}
            payload[target].append(group)
        group['itms'].append({'rt': number(rate), 'ad_amt': number(a['base']), 'iamt': number(a['igst']), 'camt': number(a['cgst']), 'samt': number(a['sgst']), 'csamt': 0})
    for (target, code, unit, rate), h in sorted(hsn.items()):
        rows[target].append([code, h['description'], UQC.get(unit, unit), float(h['qty']), number(h['total']), number(rate), number(h['base']), number(h['igst']), number(h['cgst']), number(h['sgst']), 0])
        key = 'hsn_b2b' if target.endswith('(b2b)') else 'hsn_b2c'
        bucket = payload.setdefault('hsn', {}).setdefault(key, [])
        bucket.append({'num': len(bucket) + 1, 'hsn_sc': code, 'desc': h['description'], 'uqc': unit, 'qty': float(h['qty']), 'val': number(h['total']), 'rt': number(rate), 'txval': number(h['base']), 'iamt': number(h['igst']), 'camt': number(h['cgst']), 'samt': number(h['sgst']), 'csamt': 0})
    if report['to_date'] < '2025-05-01' and 'hsn' in payload:
        payload['hsn'] = {'data': [v for values in payload['hsn'].values() for v in values]}
        for i, h in enumerate(payload['hsn']['data'], 1): h['num'] = i
    nature = {1: 'Invoices for outward supply', 6: 'Receipt Voucher', 8: 'Refund Voucher', 5: 'Credit Note'}
    for code, numbers in sorted(documents.items()):
        details = []
        for i, value in enumerate(numbers, 1):
            # One known document per interval: never pretend numbering gaps are issued/cancelled.
            rows['docs'].append([nature[code], value, value, 1, 0])
            details.append({'num': i, 'from': value, 'to': value, 'totnum': 1, 'cancel': 0, 'net_issue': 1})
        payload.setdefault('doc_issue', {'doc_det': []})['doc_det'].append({'doc_num': code, 'docs': details})
    sheets = [sheet(k, v['title'], v['headers'], rows[k]) for k, v in schema_sheets.items()]
    return sheets, payload


def inward_sheets(records, company):
    headers = ['GSTIN of supplier', 'Supplier name', 'Bill / note number', 'Document date',
               'Invoice / note value', 'Place of supply', 'Rate', 'Taxable value',
               'Integrated tax', 'Central tax', 'State/UT tax', 'Cess',
               'Proposed book ITC', 'GST excluded from book ITC', 'Supplier filing period',
               'Supplier filing status', 'Source / review']
    buckets = {'B2B': [], 'Purchase returns': [], 'Unregistered suppliers': []}
    totals = defaultdict(lambda: [ZERO] * 7)
    for r in records:
        if r['kind'] not in {'purchase_bill', 'expense', 'debit_note'}:
            continue
        d = r['data']
        gstin = str(d.get('party_gstin', ''))
        target = 'Purchase returns' if r['kind'] == 'debit_note' else 'B2B' if gstin else 'Unregistered suppliers'
        sign = Decimal('-1') if r['kind'] == 'debit_note' else Decimal('1')
        for line in document_lines(r):
            tax = sum((dec(line[h]) for h in HEADS), ZERO)
            pending = tax if line.get('itc_treatment', 'pending_review') == 'pending_review' else ZERO
            values = [dec(line.get('taxable')), dec(line['igst']), dec(line['cgst']), dec(line['sgst']), ZERO, pending, tax - pending]
            review = 'Buyer-issued debit note; reconcile with supplier credit note' if target == 'Purchase returns' else 'Entered bill; portal details unavailable'
            buckets[target].append([gstin, r['party'], r['number'], r['date'], number(sign * dec(r['amount'])),
                                    POS.get(str(d.get('place_of_supply')), d.get('place_of_supply', '')), number(line.get('gst_rate')),
                                    *[number(sign * v) for v in values[:4]], None, number(sign * pending), number(sign * (tax - pending)), None, None, review])
            for i, value in enumerate(values): totals[target][i] += sign * value
    result = [sheet('Summary', 'Purchase-book inward supplies reconciliation',
                    ['Book section', 'Taxable value', 'Integrated tax', 'Central tax', 'State/UT tax', 'Cess not captured', 'Proposed ITC', 'GST excluded from book ITC'],
                    [[k, *[number(v) if i != 4 else None for i, v in enumerate(values)]] for k, values in totals.items()] +
                    [['NET FROM BOOKS', *[number(sum((v[i] for v in totals.values()), ZERO)) if i != 4 else None for i in range(7)]]], range(1, 8))]
    result += [sheet(k, k + ' · purchase books', headers, v, (4, 7, 8, 9, 10, 11, 12, 13)) for k, v in buckets.items()]
    result.append(sheet('Portal-only data', 'GSTR-2A data that requires a portal download', ['Portal section', 'Status'],
                        [[s, 'Not available from purchase bills; obtain supplier/portal data'] for s in ['B2BA', 'CDNR / CDNRA', 'ISD / ISDA', 'TDS / TDSA', 'TCS', 'IMPG / IMPGSEZ']]))
    return result


def summary_sheets(records, report, company):
    zero = lambda: [ZERO] * 4  # taxable, IGST, CGST, SGST
    supplies = {k: zero() for k in ('a', 'c', 'e')}
    interstate = defaultdict(zero)
    inward = defaultdict(lambda: [ZERO, ZERO])
    for r in records:
        d = r['data']
        sign = Decimal('-1') if r['kind'] in {'credit_note', 'debit_note'} else Decimal('1')
        if r['kind'] in {'sales_invoice', 'pos', 'credit_note'} or d.get('advance_tax_event'):
            for l in document_lines(r):
                treatment = l.get('tax_treatment', 'taxable')
                category = 'c' if treatment in {'nil_rated', 'exempt'} else 'e' if treatment == 'non_gst' else 'a'
                values = [dec(l.get('taxable')), *[dec(l.get(h)) for h in HEADS]]
                for i, value in enumerate(values): supplies[category][i] += sign * value
                parent = (r.get('parent') or {}).get('data', {})
                place = str(d.get('place_of_supply') or parent.get('place_of_supply') or '')
                if category == 'a' and place and place != company.state_code and not (d.get('party_gstin') or parent.get('party_gstin')) and not d.get('advance_tax_event'):
                    for i, value in enumerate(values): interstate[place][i] += sign * value
        if r['kind'] in {'purchase_bill', 'expense', 'debit_note'}:
            inter = str(d.get('supplier_state') or d.get('party_gstin', '')[:2] or company.state_code) != str(d.get('place_of_supply') or company.state_code)
            for line in d.get('lines', []):
                treatment = line.get('tax_treatment', 'taxable')
                if treatment in {'nil_rated', 'exempt', 'non_gst'}:
                    inward['non-GST' if treatment == 'non_gst' else 'nil / exempt'][0 if inter else 1] += sign * dec(line.get('taxable'))
    def amounts(values): return [number(v) for v in values]
    unknown = [None] * 5
    main = [
        ['3.1(a)', 'Outward taxable supplies other than zero/nil/exempt', *amounts([max(ZERO, v) for v in supplies['a']]), None, 'From books; negative net values floored at zero for this table'],
        ['3.1(b)', 'Outward taxable supplies (zero rated)', *unknown, 'Not captured: export / SEZ classification'],
        ['3.1(c)', 'Other outward supplies (nil rated, exempted)', *amounts(supplies['c']), None, 'From posted books'],
        ['3.1(d)', 'Inward supplies liable to reverse charge', *unknown, 'Not captured: reverse-charge determination required'],
        ['3.1(e)', 'Non-GST outward supplies', *amounts(supplies['e']), None, 'From posted books'],
    ]
    result = [sheet('3.1 Supplies', '3.1 Details of outward supplies and inward supplies liable to reverse charge',
                    ['Table', 'Nature of supplies', 'Taxable value', 'Integrated tax', 'Central tax', 'State/UT tax', 'Cess', 'Basis / review'], main, (2, 3, 4, 5, 6))]
    result.append(sheet('3.1.1 ECO', '3.1.1 Supplies notified under section 9(5)',
                        ['Table', 'Nature of supplies', 'Taxable value', 'Integrated tax', 'Central tax', 'State/UT tax', 'Cess', 'Status'],
                        [[code, label, *unknown, 'Not captured; verify applicability'] for code, label in [
                            ('3.1.1(i)', 'Supplies on which e-commerce operator pays tax'), ('3.1.1(ii)', 'Supplies made through e-commerce operator')]], (2, 3, 4, 5, 6)))
    result.append(sheet('3.2 Interstate', '3.2 Interstate supplies to specified recipients',
                        ['Recipient category', 'Place of supply', 'Taxable value', 'Integrated tax', 'Status'],
                        [['Unregistered persons', POS.get(k, k), number(v[0]), number(v[1]), 'From posted books'] for k, v in sorted(interstate.items())] +
                        [['Composition taxable persons', None, None, None, 'Recipient profile not captured'], ['UIN holders', None, None, None, 'Recipient profile not captured']], (2, 3)))
    credit = [number(report['book_itc'][h]) for h in HEADS]
    itc_rows = [[code, label, None, None, None, None, 'Not captured; verify GSTR-2B and other records'] for code, label in [
        ('4(A)(1)', 'Import of goods'), ('4(A)(2)', 'Import of services'), ('4(A)(3)', 'Inward supplies liable to reverse charge'), ('4(A)(4)', 'Inward supplies from ISD')]]
    itc_rows += [['4(A)(5)', 'All other ITC · proposed book amount only', *credit, None, 'Net of book returns and excluded GST; verify eligibility and GSTR-2B'],
                 ['4(B)(1)', 'Reversals under rules 38/42/43 and section 17(5)', None, None, None, None, 'Reversal reasons not captured'],
                 ['4(B)(2)', 'Other reversals', None, None, None, None, 'Not captured'],
                 ['4(C)', 'Net ITC available (A minus B)', None, None, None, None, 'Cannot finalize without all ITC and reversal details'],
                 ['4(D)(1)', 'ITC reclaimed previously reversed under 4(B)(2)', None, None, None, None, 'Not captured'],
                 ['4(D)(2)', 'Ineligible ITC under section 16(4) / POS restriction', None, None, None, None, 'Specific ineligibility reasons not captured']]
    result.append(sheet('4 ITC', '4 Eligible ITC', ['Table', 'Details', 'Integrated tax', 'Central tax', 'State/UT tax', 'Cess', 'Basis / review'], itc_rows, (2, 3, 4, 5)))
    result.append(sheet('5 Inward exempt', '5 Exempt, nil-rated and non-GST inward supplies',
                        ['Nature of supplies', 'Interstate value', 'Intrastate value', 'Basis / review'],
                        [['From composition suppliers', None, None, 'Supplier composition profile not captured'],
                         ['Exempt and nil-rated supplies', *amounts(inward['nil / exempt']), 'From posted books'],
                         ['Non-GST supplies', *amounts(inward['non-GST']), 'From posted books']], (1, 2)))
    result.append(sheet('5.1 Interest late fee', '5.1 Interest and late fee payable',
                        ['Details', 'Integrated tax', 'Central tax', 'State/UT tax', 'Cess', 'Status'],
                        [[k, None, None, None, None, 'Not calculated; verify portal and payment dates'] for k in ['Interest', 'Late fee']], (1, 2, 3, 4)))
    result.append(sheet('6.1 Tax payment', '6.1 Payment of tax · portal settlement required',
                        ['Tax head', 'Tax payable from books', 'Paid through IGST ITC', 'Paid through CGST ITC', 'Paid through SGST ITC', 'Paid through cess ITC', 'Tax paid in cash', 'Interest paid in cash', 'Late fee paid in cash', 'Status'],
                        [[h.upper(), number(report['output'][h]), *([None] * 7), 'Actual payment not captured'] for h in HEADS] +
                        [['CESS', None, *([None] * 7), 'Cess and actual payment not captured']], range(1, 9)))
    result.append(sheet('Book estimate', 'Provisional tax set-off calculation · not actual tax paid',
                        ['Tax head', 'Output GST', 'Proposed book ITC', 'Estimated cash payable', 'Book credit remaining'],
                        [[h.upper(), number(report['output'][h]), number(report['book_itc'][h]), number(report['cash'][h]), number(report['credit_carried'][h])] for h in HEADS], range(1, 5)))
    return result


def safe_cells(ws):
    for row in ws:
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = 's'  # Company/party/reference strings must never become formulas.


def workbook(prepared, kind):
    book = Workbook()
    readme = book.active
    readme.title = 'Help Instruction' if kind == 'gstr1' else 'Read me'
    metadata = prepared['company']
    for row in [[metadata['name']], [metadata['gstin']], [prepared['from_date'] + ' to ' + prepared['to_date']], ['Amounts in INR. ' + NOTE]]:
        readme.append(row)
    for warning in prepared['info']['warnings']: readme.append([warning])
    for issue in prepared['info']['issues']: readme.append([issue['document'], issue['message']])
    readme.column_dimensions['A'].width = 80
    readme.column_dimensions['B'].width = 90
    for row in readme:
        for cell in row: cell.alignment = Alignment(wrap_text=True, vertical='top')
        readme.row_dimensions[row[0].row].height = 32
    for spec in prepared['sheets']:
        ws = book.create_sheet(spec['name'])
        official = SCHEMA['sheets'].get(spec['name']) if kind == 'gstr1' else None
        ws.append([spec['title']])
        ws.append(official['summary'] if official else [metadata['name'], metadata['gstin']])
        # GSTN expects the field headers at row 4, with data beginning at row 5.
        ws.append([None] if official else [prepared['from_date'], prepared['to_date'], 'BOOK-DERIVED DRAFT'])
        ws.append(spec['headers'])
        for row in spec['rows']: ws.append(row)
        if official:
            for i, label in enumerate(official['summary'], 1):
                if not label: continue
                field = next((j for j, h in enumerate(spec['headers']) if h and (str(label).strip().lower() == ('total ' + h).lower() or str(label).strip().lower() == h.lower())), None)
                if field is None and 'Exempted' in str(label):
                    field = next((j for j, h in enumerate(spec['headers']) if h.startswith('Exempted')), None)
                if field is not None:
                    values = spec['rows']
                    if values and spec['headers'][field] in {'Invoice Value', 'Note Value'}:
                        ref = 'Invoice Number' if 'Invoice Number' in spec['headers'] else 'Note Number'
                        ref_index = spec['headers'].index(ref)
                        # The same document value repeats once per rate in the GSTN template.
                        values = list({str(v[ref_index]): v for v in values}.values())
                    ws.cell(3, i, sum((v[field] for v in values if field < len(v) and isinstance(v[field], (int, float))), 0))
                elif str(label).startswith('No.'):
                    named = 'Invoice Number' if 'Invoices' in label else 'Note Number' if 'Notes' in label else 'GSTIN/UIN of Recipient' if 'Recipients' in label else 'HSN' if 'HSN' in label else None
                    if named in spec['headers']:
                        j = spec['headers'].index(named); ws.cell(3, i, len({str(v[j]) for v in spec['rows']}))
        ws.freeze_panes = 'A5'
        ws.auto_filter.ref = f'A4:{ws.cell(max(4, ws.max_row), len(spec["headers"])).coordinate}'
        ws.sheet_view.showGridLines = False
        ws.print_title_rows = '1:4'
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        for c in ws[4]:
            c.font = Font(bold=True, color='FFFFFF')
            c.fill = PatternFill('solid', fgColor='244F43')
            c.alignment = Alignment(wrap_text=True, vertical='center')
        ws.row_dimensions[4].height = 34
        ws['A1'].font = Font(size=13, bold=True, color='244F43')
        for row in ws.iter_rows(min_row=5):
            for c in row:
                c.alignment = Alignment(vertical='top', wrap_text=True)
                if isinstance(c.value, datetime): c.number_format = 'dd-mmm-yyyy'
                elif isinstance(c.value, (float, Decimal)) or c.column - 1 in spec['money_columns']: c.number_format = '#,##0.00;[Red]-#,##0.00'
        for j, header in enumerate(spec['headers'], 1):
            ws.column_dimensions[ws.cell(4, j).column_letter].width = min(48, max(16, len(str(header)) + 2))
        safe_cells(ws)
    safe_cells(readme)
    out = BytesIO(); book.save(out)
    return out.getvalue()


def pdf(prepared, kind):
    page = landscape(A4)
    width = page[0] - 56
    body = ParagraphStyle('GstCell', fontName='Helvetica', fontSize=7, leading=9)
    heading = ParagraphStyle('GstHeader', parent=body, fontName='Helvetica-Bold', textColor=colors.white)
    title = ParagraphStyle('GstTitle', fontName='Helvetica-Bold', fontSize=15, leading=19, spaceAfter=9)
    section = ParagraphStyle('GstSection', fontName='Helvetica-Bold', fontSize=10, leading=13, spaceBefore=14, spaceAfter=7, keepWithNext=True)
    def cell(value, style=body):
        if value is None: value = ''
        elif isinstance(value, datetime): value = value.strftime('%d-%b-%Y')
        elif isinstance(value, (float, Decimal)): value = f'{value:,.2f}'
        return Paragraph(escape(str(value)), style)
    story = [Paragraph(kind.upper().replace('GSTR', 'GSTR-') + (' · Purchase books' if kind == 'gstr2a' else ' · Preparation working paper'), title),
             cell(prepared['company']['name']), cell('GSTIN: ' + prepared['company']['gstin']),
             cell(prepared['from_date'] + ' to ' + prepared['to_date'] + ' | Amounts in INR'), Spacer(1, 9), cell(NOTE)]
    for warning in prepared['info']['warnings']: story += [Spacer(1, 4), cell(warning)]
    # GSTR-1 PDF is a review summary plus populated schedules, not an upload file.
    for spec in prepared['sheets']:
        if not spec['rows']: continue
        caption = spec['title']
        if spec['name'] in {'hsn(b2b)', 'hsn(b2c)'}:
            caption += ' · ' + ('B2B supplies' if spec['name'] == 'hsn(b2b)' else 'B2C supplies')
        story.append(Paragraph(escape(caption), section))
        headers, rows = spec['headers'], spec['rows']
        # Avoid unreadable 13–17-column PDFs: split each schedule into meaningful panels.
        keys = ['GSTIN of supplier', 'Bill / note number', 'Rate'] if kind == 'gstr2a' else ['GSTIN/UIN of Recipient', 'Invoice Number', 'Note Number', 'HSN', 'Rate']
        key_indices = [headers.index(k) for k in keys if k in headers]
        if not key_indices: key_indices = list(range(min(2, len(headers))))
        rest = [i for i in range(len(headers)) if i not in key_indices]
        chunk_size = 8 - len(key_indices)
        chunks = [list(range(len(headers)))] if len(headers) <= 8 else [key_indices + rest[i:i + chunk_size] for i in range(0, len(rest), chunk_size)]
        for indices in chunks:
            columns = [width / len(indices)] * len(indices)
            values = [[cell(headers[i], heading) for i in indices]] + [[cell(row[i]) for i in indices] for row in rows]
            table = LongTable(values, colWidths=columns, repeatRows=1, hAlign='LEFT')
            table.setStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#244f43')),
                            ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f7f5')]),
                            ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)])
            story += [table, Spacer(1, 6)]
    if prepared['info']['issues']:
        story.append(Paragraph('Preparation checks', section))
        for item in prepared['info']['issues']: story.append(cell(item['document'] + ': ' + item['message']))
    out = BytesIO()
    def footer(canvas, doc):
        canvas.setFont('Helvetica', 7)
        canvas.drawString(28, 15, 'Apex Books | Book-derived draft | Not filed')
        canvas.drawRightString(page[0] - 28, 15, f'Page {doc.page}')
    SimpleDocTemplate(out, pagesize=page, leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=30).build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()


def export_response(kind, data, fmt):
    prepared = data['_export']
    if fmt == 'json':
        if kind != 'gstr1':
            raise HTTPException(422, 'Only GSTR-1 preparation JSON is supported. Purchase books are not portal GSTR-2A; GSTR-3B needs reviewed portal and payment data.')
        if not prepared['info']['json_available']:
            raise HTTPException(422, {'message': 'Resolve the preparation checks before generating GSTR-1 JSON.', 'issues': prepared['info']['issues']})
        content = json.dumps(prepared['payload'], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        media = 'application/json'
    elif fmt == 'xlsx':
        content = workbook(prepared, kind); media = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        content = pdf(prepared, kind); media = 'application/pdf'
    prefix = 'gstr2a-purchase-books' if kind == 'gstr2a' else kind + '-preparation'
    filename = f'{prefix}-{prepared["from_date"]}-{prepared["to_date"]}.{fmt}'
    return Response(content, media_type=media, headers={'Content-Disposition': f'attachment; filename="{filename}"'})
