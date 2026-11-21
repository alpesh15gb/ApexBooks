import io
import re
from accounting import applied_totals_by_document, company_for, current_user, db
from datetime import date as DateType
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from models import CompanyTaxProfile, Journal, JournalLine, LedgerAccount, Record, RecordPosting, User
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from report_basis import AGEING_BASIS
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session


router = APIRouter()


@router.get('/api/companies/{company_id}/trial-balance')
def trial_balance(company_id: str, through: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    accounts, totals, _ = account_balances(company_id, DateType.min, through, session)
    result = [{'id': a.id, 'code': a.code, 'name': a.name, 'category': a.category, 'debit': str(max(totals[a.id], Decimal('0'))), 'credit': str(max(-totals[a.id], Decimal('0')))} for a in accounts]
    return {'through': through.isoformat(), 'accounts': result, 'total_debit': str(sum((max(value, Decimal('0')) for value in totals.values()), Decimal('0'))), 'total_credit': str(sum((max(-value, Decimal('0')) for value in totals.values()), Decimal('0')))}


def account_balances(company_id, from_date, to_date, session):
    # One SQL statement keeps account membership, period and closing balances in
    # the same snapshot under PostgreSQL READ COMMITTED. Posting can create an
    # account between separate SELECTs, causing missing accounts or mixed totals.
    movement = JournalLine.debit - JournalLine.credit
    balances = (select(JournalLine.account_id,
        func.sum(case((Journal.date >= from_date, movement), else_=0)).label('period'),
        func.sum(case((Journal.date >= DateType(1900, 1, 1), movement), else_=0)).label('cumulative'))
        .join(Journal, (Journal.id == JournalLine.journal_id) & (Journal.company_id == JournalLine.company_id))
        .where(Journal.company_id == company_id, JournalLine.company_id == company_id, Journal.date <= to_date)
        .group_by(JournalLine.account_id).subquery())
    rows = session.execute(select(LedgerAccount, func.coalesce(balances.c.period, 0),
        func.coalesce(balances.c.cumulative, 0))
        .outerjoin(balances, balances.c.account_id == LedgerAccount.id)
        .where(LedgerAccount.company_id == company_id).order_by(LedgerAccount.code)).all()
    return ([account for account, _, _ in rows],
        {account.id: period for account, period, _ in rows},
        {account.id: cumulative for account, _, cumulative in rows})


def account_movements(company_id, from_date, to_date, session):
    accounts, period, _ = account_balances(company_id, from_date, to_date, session)
    return accounts, period


@router.get('/api/companies/{company_id}/reports/financial')
def financial_report(company_id: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    accounts, period, cumulative = account_balances(company_id, from_date, to_date, session)
    rows = [{'code': a.code, 'name': a.name, 'category': a.category,
             'period_balance': str(period[a.id] if a.category in {'asset', 'expense'} else -period[a.id]),
             'closing_balance': str(cumulative[a.id] if a.category in {'asset', 'expense'} else -cumulative[a.id])}
            for a in accounts]
    income = sum((-period[a.id] for a in accounts if a.category == 'income'), Decimal('0'))
    expense = sum((period[a.id] for a in accounts if a.category == 'expense'), Decimal('0'))
    assets = sum((cumulative[a.id] for a in accounts if a.category == 'asset'), Decimal('0'))
    liabilities = sum((-cumulative[a.id] for a in accounts if a.category == 'liability'), Decimal('0'))
    equity = sum((-cumulative[a.id] for a in accounts if a.category == 'equity'), Decimal('0'))
    cumulative_income = sum((-cumulative[a.id] for a in accounts if a.category == 'income'), Decimal('0'))
    cumulative_expense = sum((cumulative[a.id] for a in accounts if a.category == 'expense'), Decimal('0'))
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(), 'accounts': rows,
            'income': str(income), 'expenses': str(expense), 'net_profit': str(income - expense),
            'assets': str(assets), 'liabilities': str(liabilities), 'equity': str(equity),
            'retained_earnings': str(cumulative_income - cumulative_expense),
            'balance_difference': str(assets - liabilities - equity - cumulative_income + cumulative_expense)}


@router.get('/api/companies/{company_id}/reports/parties')
def party_report(company_id: str, from_date: DateType, to_date: DateType, party: str = Query(default='', max_length=120), user: User = Depends(current_user), session: Session = Depends(db), include_corrections: bool = False):
    import book_services as services
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    postings = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    kinds = {'sales_invoice', 'credit_note', 'payment_in', 'purchase_bill', 'debit_note', 'payment_out', 'advance_application','opening_receivable','opening_payable','credit_application','customer_refund','supplier_refund'}
    records = list(session.scalars(select(Record).where(Record.company_id == company_id, Record.id.in_(postings), Record.kind.in_(kinds), Record.date <= to_date).order_by(Record.date, Record.number, Record.id)))
    selected = party.strip().casefold()
    from statement_order import record_key, posting_timestamp, ORDERING_NOTE
    records = sorted((r for r in records if not selected or r.name.strip().casefold() == selected), key=record_key)
    receivable = payable = Decimal('0')
    opening_receivable = opening_payable = Decimal('0')
    rows = []
    customer_receipts = Decimal('0')
    for r in records:
        kind = r.kind
        if r.kind == 'payment_in' and r.date >= from_date:
            customer_receipts += r.amount
        if r.data.get('is_advance'):
            if r.kind != 'payment_in': continue
            kind = 'customer_advance_receipt'
        elif r.kind == 'payment_in' and r.data.get('receipt_purpose') == 'unallocated':
            kind = 'unallocated_customer_receipt'
        elif r.kind in {'sales_invoice','opening_receivable'}: receivable += r.amount
        elif r.kind in {'credit_note', 'payment_in'}: receivable -= r.amount - (Decimal(str(r.data.get('unallocated_credit',0))) if r.kind in {'credit_note','debit_note'} else Decimal('0'))
        elif r.kind in {'purchase_bill','opening_payable'}: payable += r.amount
        elif r.kind in {'advance_application','credit_application'} and r.data.get('payment_kind') == 'payment_in': receivable -= r.amount
        elif r.kind in {'advance_application','credit_application'}: payable -= r.amount
        elif r.kind in {'debit_note','payment_out'}: payable -= r.amount - (Decimal(str(r.data.get('unallocated_credit',0))) if r.kind in {'credit_note','debit_note'} else Decimal('0'))
        if r.date < from_date:
            opening_receivable, opening_payable = receivable, payable
        else:
            rows.append({'date': r.date.isoformat(), 'party': r.name, 'kind': kind, 'number': r.number,
                         'amount': str(r.amount), 'receivable': str(receivable), 'payable': str(payable), 'posting_timestamp': posting_timestamp(r)})
    from party_statements import correction_history
    history = correction_history(services, company_id, selected, from_date, to_date, session) if include_corrections else []
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(), 'party': party.strip(),
            'opening_receivable': str(opening_receivable), 'opening_payable': str(opening_payable),
            'closing_receivable': str(receivable), 'closing_payable': str(payable), 'rows': rows, 'ordering_note': ORDERING_NOTE,
            'customer_receipts': str(customer_receipts), 'correction_history': history}


@router.get('/api/companies/{company_id}/reports/advances')
def advances_report(company_id: str, as_of: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    posted = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    records = list(session.scalars(select(Record).where(Record.company_id == company_id, Record.id.in_(posted), Record.date <= as_of,
        Record.kind.in_(['payment_in', 'payment_out', 'advance_application','advance_refund'])).order_by(Record.date, Record.number, Record.id)))
    used = {}
    for r in records:
        if r.kind in {'advance_application','advance_refund'}: used[r.data.get('advance_id')] = used.get(r.data.get('advance_id'), Decimal('0')) + r.amount
    rows = [{'id': r.id, 'date': r.date.isoformat(), 'number': r.number, 'party': r.name,
        'side': 'customer' if r.kind == 'payment_in' else 'supplier', 'amount': str(r.amount),
        'applied': str(used.get(r.id, Decimal('0'))), 'available': str(r.amount - used.get(r.id, Decimal('0')))}
        for r in records if r.kind in {'payment_in', 'payment_out'} and r.data.get('is_advance')]
    return {'as_of': as_of.isoformat(), 'rows': rows, 'totals': {side: str(sum((Decimal(r['available']) for r in rows if r['side'] == side), Decimal('0'))) for side in ('customer', 'supplier')}}


@router.get('/api/companies/{company_id}/reports/advances.{fmt}')
def advances_report_export(company_id: str, fmt: str, as_of: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    report = advances_report(company_id, as_of, user, session)
    rows = [[r[key] for key in ('date', 'number', 'party', 'side', 'amount', 'applied', 'available')] for r in report['rows']]
    company = company_for(company_id, user, session)
    return export_table(company.name, 'Advances as of ' + as_of.isoformat(), ['Date', 'Reference', 'Party', 'Side', 'Original', 'Applied/refunded', 'Available'], rows, fmt, 'apex-advances')


@router.get('/api/companies/{company_id}/reports/ageing')
def ageing_report(company_id: str, as_of: DateType, party: str = Query(default='', max_length=120),
                  user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    posted = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    documents = list(session.scalars(select(Record).where(Record.company_id == company_id,
        Record.id.in_(posted), Record.kind.in_(['sales_invoice', 'purchase_bill','opening_receivable','opening_payable']), Record.date <= as_of)
        .order_by(Record.name, Record.date, Record.number, Record.id)))
    applied = applied_totals_by_document(company_id, session, as_of)
    bucket_names = ('0-30', '31-60', '61-90', '91+')
    buckets = {side: {name: Decimal('0') for name in bucket_names} for side in ('receivable', 'payable')}
    totals = {'receivable': Decimal('0'), 'payable': Decimal('0')}
    selected = party.strip().casefold()
    rows = []
    for document in documents:
        if selected and document.name.strip().casefold() != selected: continue
        settled = applied.get(document.id, Decimal('0'))
        remaining = document.amount - settled
        if remaining <= 0: continue
        age_days = (as_of - document.date).days
        bucket = bucket_names[0 if age_days <= 30 else 1 if age_days <= 60 else 2 if age_days <= 90 else 3]
        side = 'receivable' if document.kind in {'sales_invoice','opening_receivable'} else 'payable'
        buckets[side][bucket] += remaining
        totals[side] += remaining
        try: due_date = DateType.fromisoformat(document.data.get('due_date') or '')
        except (TypeError, ValueError): due_date = None
        rows.append({'document_id': document.id, 'party': document.name, 'kind': document.kind,
            'number': document.number, 'date': document.date.isoformat(), 'age_days': age_days,
            'due_date': due_date.isoformat() if due_date else None,
            'overdue_days': max(0, (as_of - due_date).days) if due_date else None,
            'bucket': bucket, 'original_amount': str(document.amount), 'applied_amount': str(settled),
            'outstanding': str(remaining)})
    return {'as_of': as_of.isoformat(), 'party': party.strip(), 'rows': rows, 'basis': AGEING_BASIS,
        'totals': {side: str(value) for side, value in totals.items()},
        'buckets': {side: {name: str(value) for name, value in amounts.items()} for side, amounts in buckets.items()}}


def export_table(company_name, title, headers, rows, fmt, filename, *, notes=(), currency_columns=()):
    out = io.BytesIO()
    currency_columns=set(currency_columns)
    display_headers=[header+' (INR)' if header in currency_columns else header for header in headers]
    if currency_columns: notes=('Currency: INR. Monetary columns are denominated in Indian rupees.',*notes)
    if fmt == 'xlsx':
        book = Workbook(); sheet = book.active; sheet.title = re.sub(r'[\\/*?:\[\]]', ' ', title)[:31] or 'Report'
        sheet.append([company_name]); sheet.append([title]); sheet.append(display_headers)
        text_columns = {'Name', 'Description', 'Code', 'HSN', 'HSN / SAC', 'GSTIN', 'Phone', 'Email', 'Number', 'Document', 'Date', 'Type', 'Party', 'Account', 'Unit', 'Bucket', 'Category', 'Item', 'Reference', 'Particulars', 'Vch Type', 'Vch No.', 'Barcode', 'HSN/SAC', 'Address', 'Item type', 'Tax treatment', 'Metric', 'Stock tracked'}
        for row in rows:
            prepared = []
            for header, value in zip(headers, row):
                if header not in text_columns and isinstance(value, str) and re.fullmatch(r'-?\d+(?:\.\d+)?', value):
                    prepared.append(float(value) if '.' in value else int(value))
                else:
                    prepared.append(value)
            sheet.append(prepared)
        # Preserve literal strings, including formula-like names and Excel error literals.
        # Numeric amount/quantity conversion above remains explicit and unchanged.
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str): cell.data_type = 's'
        sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
        sheet['A1'].font = Font(name='Calibri', size=16, bold=True, color='244F43')
        sheet['A2'].font = Font(name='Calibri', size=11, color='52605B')
        for cell in sheet[3]:
            cell.fill = PatternFill('solid', fgColor='244F43')
            cell.font = Font(name='Calibri', bold=True, color='FFFFFF')
            cell.alignment = Alignment(vertical='center')
        sheet.row_dimensions[3].height = 24
        for row in sheet.iter_rows(min_row=4):
            for cell in row:
                if isinstance(cell.value, (int, float)):
                    cell.number_format = '#,##0.00' if isinstance(cell.value, float) or headers[cell.column-1] in currency_columns else '0'
                    cell.alignment = Alignment(horizontal='right')
                if cell.row % 2 == 0:
                    cell.fill = PatternFill('solid', fgColor='F5F8F5')
        sheet.freeze_panes = 'A4'
        sheet.sheet_view.showGridLines = False
        sheet.auto_filter.ref = f'A3:{sheet.cell(3, len(headers)).column_letter}{sheet.max_row}'
        for column_index, column in enumerate(sheet.columns, start=1):
            letter = sheet.cell(3, column_index).column_letter
            sheet.column_dimensions[letter].width = min(42, max(14, max((len(str(cell.value or '')) for cell in column), default=14) + 2))
        if notes:
            note_sheet=book.create_sheet('Report notes');note_sheet.column_dimensions['A'].width=110
            for index,note in enumerate(notes,1):
                cell=note_sheet.cell(index,1,str(note));cell.data_type='s';cell.alignment=Alignment(wrap_text=True,vertical='top');note_sheet.row_dimensions[index].height=60
        book.save(out)
        media = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif fmt == 'pdf':
        from html import escape
        page = landscape(A4) if len(headers) > 6 else A4
        width = page[0] - 50
        first = width*.72 if len(headers)==2 else min(145, width * .27)
        column_widths = [first] + [(width - first) / (len(headers) - 1)] * (len(headers) - 1)
        if headers == ['Party', 'Type', 'Document', 'Date', 'Age days', 'Original', 'Applied', 'Outstanding', 'Bucket', 'Due date', 'Overdue days']:
            weights = [1.8, 1.1, 1.4, 1.1, .7, 1.05, .95, 1.2, .7, 1.1, .8]
            column_widths = [width * weight / sum(weights) for weight in weights]
        regular_font,bold_font='Helvetica','Helvetica-Bold'
        if currency_columns:
            import party_report_pdf  # Register the bundled, embedded report fonts.
            regular_font,bold_font='ApexReport','ApexReportBold'
        body_style = ParagraphStyle('ReportCell', fontName=regular_font, fontSize=8 if currency_columns else 7, leading=11 if currency_columns else 9)
        heading_style = ParagraphStyle('ReportHeading', parent=body_style, fontName=bold_font, textColor=colors.white)
        def cell(value, style): return Paragraph(escape(str(value if value is not None else '')), style)
        from currency import format_inr
        from reportlab.lib.enums import TA_RIGHT
        numeric_style=ParagraphStyle('ReportNumber',parent=body_style,alignment=TA_RIGHT)
        def presented(header,value):
            if not currency_columns or value in ('',None):return value
            if header in currency_columns:return format_inr(value)
            if header in {'Date','Due date'}:
                try:return DateType.fromisoformat(str(value)).strftime('%d-%b-%Y')
                except ValueError:return value
            if header=='Type':return {'payment_in':'Receipt','payment_out':'Payment','bank_transfer':'Bank transfer'}.get(str(value),str(value).replace('_',' ').capitalize())
            return value
        table_rows = [[cell(value, heading_style) for value in display_headers]]
        table_rows += [[cell(presented(header,value),numeric_style if header in currency_columns else body_style) for header,value in zip(headers,row)] for row in rows]
        table = LongTable(table_rows, colWidths=column_widths, repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#244f43')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f8f5')]),
            ('LINEBELOW', (0, 0), (-1, -1), .2, colors.HexColor('#dde6de')), ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
        document = SimpleDocTemplate(out, pagesize=page, leftMargin=25, rightMargin=25, topMargin=30, bottomMargin=30, title=title)
        def footer(canvas,doc):
            if currency_columns:
                canvas.saveState();canvas.setFont(regular_font,7);canvas.drawString(25,15,title+' | INR');canvas.drawRightString(page[0]-25,15,'Page '+str(doc.page));canvas.restoreState()
        document.build([Paragraph(escape(company_name), ParagraphStyle('ReportTitle', fontName=bold_font, fontSize=12, leading=16)),
                        Paragraph(escape(title), body_style)]+[Paragraph(escape(str(note)),body_style) for note in notes]+[Spacer(1, 12), table], onFirstPage=footer, onLaterPages=footer)
        media = 'application/pdf'
    else: raise HTTPException(404, 'Unsupported export format')
    return Response(out.getvalue(), media_type=media, headers={'Content-Disposition': f'attachment; filename="{filename}.{fmt}"'})


@router.get('/api/companies/{company_id}/reports/financial.{fmt}')
def export_financial(company_id: str, fmt: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    data = financial_report(company_id, from_date, to_date, user, session)
    rows = [[r['code'], r['name'], r['category'], r['period_balance'], r['closing_balance']] for r in data['accounts']]
    rows += [['', 'Net profit', '', data['net_profit'], ''], ['', 'Assets', '', '', data['assets']],
             ['', 'Liabilities', '', '', data['liabilities']], ['', 'Equity and retained earnings', '', '', str(Decimal(data['equity']) + Decimal(data['retained_earnings']))]]
    return export_table(company.name, f"Financial report {from_date} to {to_date}", ['Code', 'Account', 'Category', 'Period', 'Closing'], rows, fmt, 'financial-report')


@router.get('/api/companies/{company_id}/reports/parties.{fmt}')
def export_parties(company_id: str, fmt: str, from_date: DateType, to_date: DateType, party: str = Query(default='', max_length=120), user: User = Depends(current_user), session: Session = Depends(db), include_corrections: bool = False):
    company = company_for(company_id, user, session)
    data = party_report(company_id, from_date, to_date, party, user, session, include_corrections)
    if fmt == 'pdf':
        from party_report_pdf import render
        return Response(render(company.name, data), media_type='application/pdf', headers={'Content-Disposition':'attachment; filename="party-statement.pdf"'})
    rows = [[r[key] for key in ('date', 'party', 'kind', 'number', 'amount', 'receivable', 'payable')] for r in data['rows']]
    if data['correction_history']:
        rows.append(['', 'Correction history', '', '', '', '', ''])
        rows.extend([r['date'], r['party'], r['details'], r['number'], '', '', ''] for r in data['correction_history'])
    return export_table(company.name, f"Party statement {from_date} to {to_date}", ['Date', 'Party', 'Type', 'Number', 'Amount', 'Receivable', 'Payable'], rows, fmt, 'party-statement', notes=[data['ordering_note']])


@router.get('/api/companies/{company_id}/reports/ageing.{fmt}')
def export_ageing(company_id: str, fmt: str, as_of: DateType, party: str = Query(default='', max_length=120),
                  user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    data = ageing_report(company_id, as_of, party, user, session)
    rows = [[r[key] for key in ('party', 'kind', 'number', 'date', 'age_days', 'original_amount', 'applied_amount', 'outstanding', 'bucket', 'due_date', 'overdue_days')]
            for r in data['rows']]
    rows += [['', 'Total receivable', '', '', '', '', '', data['totals']['receivable'], '', '', ''],
             ['', 'Total payable', '', '', '', '', '', data['totals']['payable'], '', '', '']]
    return export_table(company.name, f'Document ageing as of {as_of}',
        ['Party', 'Type', 'Document', 'Date', 'Age days', 'Original', 'Applied', 'Outstanding', 'Bucket', 'Due date', 'Overdue days'],
        rows, fmt, 'document-ageing', notes=[AGEING_BASIS], currency_columns=['Original','Applied','Outstanding'])


@router.get('/api/companies/{company_id}/reports/register')
def transaction_register(company_id: str, from_date: DateType, to_date: DateType, group: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    if group not in {'sales','purchases','expenses'}: raise HTTPException(422, 'Choose sales, purchases or expenses')
    kinds = {'sales_invoice','pos','credit_note'} if group=='sales' else {'expense'} if group=='expenses' else {'purchase_bill','debit_note'}
    postings = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    records = session.scalars(select(Record).where(Record.company_id == company_id, Record.id.in_(postings), Record.kind.in_(kinds), Record.date >= from_date, Record.date <= to_date).order_by(Record.date, Record.number, Record.id))
    rows = []
    total = Decimal('0')
    for record in records:
        sign = -1 if record.kind in {'credit_note', 'debit_note'} else 1
        amount = sign * record.amount
        total += amount
        rows.append({'date': record.date.isoformat(), 'kind': record.kind, 'number': record.number,
                     'party': record.name, 'taxable': str(sign * Decimal(str(record.data.get('taxable', record.amount)))),
                     'cgst': str(sign * Decimal(str(record.data.get('cgst', 0)))),
                     'sgst': str(sign * Decimal(str(record.data.get('sgst', 0)))),
                     'igst': str(sign * Decimal(str(record.data.get('igst', 0)))),
                     'supplier_tax': str(sign * Decimal(str(record.data.get('supplier_tax', 0)))),
                     'input_ineligible': str(sign * Decimal(str(record.data.get('input_tax_ineligible', 0)))), 'amount': str(amount)})
    return {'group': group, 'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(), 'rows': rows, 'total': str(total)}


@router.get('/api/companies/{company_id}/reports/register.{fmt}')
def export_transaction_register(company_id: str, fmt: str, from_date: DateType, to_date: DateType, group: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    data = transaction_register(company_id, from_date, to_date, group, user, session)
    keys = ('date', 'kind', 'number', 'party', 'taxable', 'cgst', 'sgst', 'igst', 'supplier_tax', 'input_ineligible', 'amount')
    rows = [[row[key] for key in keys] for row in data['rows']]
    rows.append(['', '', '', 'Net total', '', '', '', '', '', '', data['total']])
    return export_table(company.name, f"{group.title()} register {from_date} to {to_date}", ['Date', 'Type', 'Number', 'Party', 'Subtotal', 'CGST', 'SGST', 'IGST', 'Supplier tax', 'GST in cost', 'Total'], rows, fmt, f'{group}-register')


@router.get('/api/companies/{company_id}/reports/summary')
def report_summary(company_id: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    postings = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    records = list(session.scalars(select(Record).where(Record.company_id == company_id, Record.id.in_(postings), Record.date >= from_date, Record.date <= to_date)))
    def total(kinds): return sum((r.amount for r in records if r.kind in kinds), Decimal('0'))
    sales = total({'sales_invoice', 'pos'}) - total({'credit_note'})
    purchases = total({'purchase_bill'}) - total({'debit_note'})
    expenses = total({'expense'})
    receipts = total({'payment_in','pos','supplier_refund'}) + sum((r.amount for r in records if r.kind=='advance_refund' and r.data.get('payment_kind')=='payment_out'),Decimal('0'))
    payments = total({'payment_out','expense','customer_refund'}) + sum((r.amount for r in records if r.kind=='advance_refund' and r.data.get('payment_kind')=='payment_in'),Decimal('0'))
    outstanding_rows = list(session.scalars(select(Record).where(Record.company_id == company_id,
        Record.id.in_(postings), Record.date <= to_date,
        Record.kind.in_(['sales_invoice', 'purchase_bill','opening_receivable','opening_payable']))))
    applied = applied_totals_by_document(company_id, session, to_date)
    receivable = payable = Decimal('0')
    for r in outstanding_rows:
        remaining = max(Decimal('0'), r.amount - applied.get(r.id, Decimal('0')))
        if r.kind in {'sales_invoice','opening_receivable'}: receivable += remaining
        else: payable += remaining
    profile = session.get(CompanyTaxProfile, company_id)
    gst = None
    if not profile or profile.mode == 'regular':
        def tax_total(kinds, key): return sum((Decimal(str(r.data.get(key, 0))) for r in records if r.kind in kinds), Decimal('0'))
        def pending_total(kinds, key): return sum((Decimal(str(r.data.get('pending_input_' + key, r.data.get(key, 0)))) for r in records if r.kind in kinds), Decimal('0'))
        gst = {key: str(tax_total({'sales_invoice','pos','payment_in','advance_application','advance_refund'}, key) - tax_total({'credit_note'}, key)) for key in ('cgst', 'sgst', 'igst')}
        gst['input_pending_review'] = {key: str(pending_total({'purchase_bill','expense'}, key) - pending_total({'debit_note'}, key)) for key in ('cgst', 'sgst', 'igst')}
        gst['input_ineligible_in_cost'] = str(tax_total({'purchase_bill','expense'}, 'input_tax_ineligible') - tax_total({'debit_note'}, 'input_tax_ineligible'))
        def outward_value(kinds, field):
            return sum((Decimal(str(r.data.get(field, r.data.get('taxable', 0) if field == 'taxable_supply_value' else 0)))
                for r in records if r.kind in kinds), Decimal('0'))
        gst['outward_supply_values'] = {key: str(outward_value({'sales_invoice', 'pos'}, field) - outward_value({'credit_note'}, field))
            for key, field in (('taxable', 'taxable_supply_value'), ('nil_rated', 'nil_rated_value'), ('exempt', 'exempt_value'), ('non_gst', 'non_gst_value'))}
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(), 'tax_mode': profile.mode if profile else 'regular', 'sales': str(sales), 'purchases': str(purchases), 'expenses': str(expenses), 'receipts': str(receipts), 'payments': str(payments), 'receivables': str(receivable), 'payables': str(payable), 'gst': gst, 'posted_records': len(records)}


@router.get('/api/companies/{company_id}/reports/summary.{fmt}')
def export_summary(company_id: str, fmt: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    data = report_summary(company_id, from_date, to_date, user, session)
    rows = [('Period', f"{data['from_date']} to {data['to_date']}")]
    rows += [(label, data[key]) for key, label in [('sales', 'Net sales'), ('purchases', 'Net purchases'), ('expenses', 'Expenses'), ('receipts', 'Payments received'), ('payments', 'Payments out'), ('receivables', 'Receivables as of ' + data['to_date']), ('payables', 'Payables as of ' + data['to_date'])]]
    if data['gst']:
        rows += [('Output ' + key.upper(), data['gst'][key]) for key in ('cgst', 'sgst', 'igst')]
        rows += [('Input ' + key.upper() + ' pending review', data['gst']['input_pending_review'][key]) for key in ('cgst', 'sgst', 'igst')]
        rows.append(('Supplier GST included in cost', data['gst']['input_ineligible_in_cost']))
        rows += [(label, data['gst']['outward_supply_values'][key]) for key, label in (('taxable', 'Taxable outward value'), ('nil_rated', 'Nil-rated outward value'), ('exempt', 'Exempt outward value'), ('non_gst', 'Non-GST outward value'))]
    return export_table(company.name, 'Posted transaction summary', ['Metric', 'Value'], rows, fmt, f'summary.{fmt}')


@router.get('/api/companies/{company_id}/export.{fmt}')
def export(company_id: str, fmt: str, kind: str = '', user: User = Depends(current_user), session: Session = Depends(db)):
    c = company_for(company_id, user, session)
    q = select(Record).where(Record.company_id == company_id, Record.kind.not_in(('recurring_template', 'pos_register_session', 'pos_register_movement','inventory_setup')))
    if kind: q = q.where(Record.kind == kind)
    rows = list(session.scalars(q.order_by(Record.date.desc())))
    out = io.BytesIO()
    if fmt == 'xlsx':
        book = Workbook(); sheet = book.active; sheet.title = 'Register'; sheet.append(['Date', 'Type', 'Number', 'Party / name', 'Amount (INR)'])
        for r in rows: sheet.append([r.date.isoformat(), r.kind, r.number, r.name, float(r.amount)])
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str): cell.data_type = 's'
        book.save(out); media = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif fmt == 'pdf':
        pdf = canvas.Canvas(out, pagesize=A4); pdf.setTitle('Apex Books register'); pdf.drawString(40, 800, f'{c.name} — Transaction register'); y = 770
        for r in rows:
            if y < 45: pdf.showPage(); y = 800
            pdf.drawString(40, y, f'{r.date}  {r.kind}  {r.number}  {r.name}'[:85]); pdf.drawRightString(555, y, str(r.amount)); y -= 20
        pdf.save(); media = 'application/pdf'
    else: raise HTTPException(404, 'Unsupported export format')
    return Response(out.getvalue(), media_type=media, headers={'Content-Disposition': f'attachment; filename="register.{fmt}"'})
