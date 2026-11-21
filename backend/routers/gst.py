from accounting import DOCUMENTS, company_for, current_user, db
from datetime import date as DateType
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from models import CompanyTaxProfile, Record, RecordPosting, User
from sqlalchemy import select
from sqlalchemy.orm import Session


router = APIRouter()


@router.get('/api/companies/{company_id}/reports/gst')
def gst_report(company_id: str, from_date: DateType, to_date: DateType,
               user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    profile = session.get(CompanyTaxProfile, company_id)
    posted = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    kinds = ('sales_invoice','pos','credit_note','purchase_bill','debit_note','expense','payment_in','advance_application','advance_refund')
    documents = list(session.scalars(select(Record).where(Record.company_id == company_id,
        Record.id.in_(posted), Record.kind.in_(kinds), Record.date >= from_date, Record.date <= to_date)))
    regular = [record for record in documents if record.data.get('tax_mode') == 'regular' and (record.kind in DOCUMENTS or record.data.get('advance_tax_event'))]
    grouped = {}
    for record in regular:
        outward = record.kind in {'sales_invoice','pos','credit_note','payment_in','advance_application','advance_refund'}
        side = 'outward' if outward else 'inward'
        sign = -1 if record.kind in {'credit_note', 'debit_note'} else 1
        for line in record.data.get('lines', []):
            treatment = line.get('tax_treatment', 'taxable')
            rate = str(Decimal(str(line.get('gst_rate', 0))))
            key = (side, treatment, rate)
            if key not in grouped:
                grouped[key] = {'taxable': Decimal('0'), 'tax': Decimal('0'),
                                'pending_input': Decimal('0'), 'ineligible_input': Decimal('0')}
            values = grouped[key]
            taxable = Decimal(str(line.get('taxable', 0))) * sign
            tax = Decimal(str(line.get('tax', 0))) * sign
            values['taxable'] += taxable
            values['tax'] += tax
            if not outward:
                values['pending_input' if line.get('itc_treatment') == 'pending_review' else 'ineligible_input'] += tax
    rows = [{'side': side, 'treatment': treatment, 'gst_rate': rate,
             **{field: str(value) for field, value in values.items()}}
            for (side, treatment, rate), values in sorted(grouped.items(),
                key=lambda item: (item[0][0], item[0][1], Decimal(item[0][2])))]
    totals = {side: {field: str(sum((values[field] for key, values in grouped.items() if key[0] == side), Decimal('0')))
                     for field in ('taxable', 'tax', 'pending_input', 'ineligible_input')}
              for side in ('outward', 'inward')}
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(),
            'applicable': bool(profile and profile.mode == 'regular') or bool(regular),
            'rows': rows, 'totals': totals, 'document_count': len(regular),
            'note': 'Posted-document tax analysis for review; not a filed GST return.'}


@router.get('/api/companies/{company_id}/reports/gst.{fmt}')
def export_gst(company_id: str, fmt: str, from_date: DateType, to_date: DateType,
               user: User = Depends(current_user), session: Session = Depends(db)):
    from routers.reports import export_table
    company = company_for(company_id, user, session)
    data = gst_report(company_id, from_date, to_date, user, session)
    rows = [[row['side'].title(), row['treatment'].replace('_', ' ').title(), row['gst_rate'],
             row['taxable'], row['tax'], row['pending_input'], row['ineligible_input']]
            for row in data['rows']]
    if data['applicable']:
        for side in ('outward', 'inward'):
            totals = data['totals'][side]
            rows.append([side.title() + ' total', '', '', totals['taxable'], totals['tax'],
                         totals['pending_input'], totals['ineligible_input']])
    if not data['applicable']: rows.append(['GST not applicable for this company and period', '', '', '', '', '', ''])
    return export_table(company.name, f'GST analysis {from_date} to {to_date}',
        ['Side', 'Classification', 'GST rate %', 'Supply value', 'Tax', 'Input pending review', 'Input in cost'],
        rows, fmt, 'gst-analysis')
