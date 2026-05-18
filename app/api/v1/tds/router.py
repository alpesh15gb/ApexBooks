from datetime import date, datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.core.security import current_principal
from app.api.v1.deps import current_tenant
from app.models.accounting import PaymentModel, InvoiceModel, GLEntryModel
from app.services.audit_service import AuditLog

router = APIRouter(prefix='/tds', tags=['TDS'])

TDS_SECTIONS = [
    {'code': '194', 'name': '194 - Salary / Wages', 'rate': 10},
    {'code': '194A', 'name': '194A - Interest other than securities', 'rate': 10},
    {'code': '194C', 'name': '194C - Payments to contractors', 'rate': 2},
    {'code': '194H', 'name': '194H - Commission / Brokerage', 'rate': 5},
    {'code': '194I', 'name': '194I - Rent on land / building / furniture', 'rate': 10},
    {'code': '194J', 'name': '194J - Professional / Technical fees', 'rate': 10},
    {'code': '194LA', 'name': '194LA - Compensation on acquisition of immovable property', 'rate': 10},
]


@router.get('/sections')
def tds_sections(tenant_id: str = Depends(current_tenant)):
    return ok({'sections': TDS_SECTIONS})


@router.post('/deductions')
def create_deduction(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Record a TDS deduction linked to a payment."""
    payment_id = payload.get('payment_id')
    section_code = payload.get('section_code')
    amount = Decimal(str(payload.get('amount', 0)))
    party_id = payload.get('party_id')

    if not payment_id or not party_id:
        raise APIError('MISSING_FIELDS', 'payment_id and party_id are required', status_code=400)

    # Find payment
    payment = db.query(PaymentModel).filter_by(
        tenant_id=principal['tenant_id'], payment_id=payment_id
    ).first()
    if not payment:
        raise APIError('PAYMENT_NOT_FOUND', f'Payment {payment_id} not found', status_code=404)

    if payment.status == 'Voided':
        raise APIError('VOIDED_PAYMENT', 'Cannot deduct TDS on voided payment', status_code=400)

    # Validate section
    section = next((s for s in TDS_SECTIONS if s['code'] == section_code), None)
    if not section:
        raise APIError('INVALID_TDS_SECTION', f'Unknown TDS section: {section_code}', status_code=400)

    # Update payment TDS fields
    payment.tds_applicable = True
    payment.tds_amount = float(payment.tds_amount or 0) + float(amount)
    payment.net_amount = float(payment.amount) - float(payment.tds_amount)

    db.flush()

    # Create TDS payable GL entry
    from app.models.e2e import AccountModel
    gl_entry = GLEntryModel(
        tenant_id=principal['tenant_id'],
        posting_date=payment.payment_date,
        account='TDS Payable',
        party_id=party_id,
        voucher_type='tds_deduction',
        voucher_id=f'TDS-{payment_id}-{section_code}',
        debit=Decimal('0'),
        credit=amount,
        remarks=f'TDS {section_code} deducted on payment {payment_id}'
    )
    db.add(gl_entry)
    db.flush()

    # Audit log
    audit = AuditLog(db)
    audit.log(principal['tenant_id'], principal['user_id'],
              'TDS_DEDUCTED', 'tds_deduction', gl_entry.id,
              {'payment_id': payment_id, 'section': section_code, 'amount': float(amount)})

    return ok({
        'tds_id': f'TDS-{payment_id}-{section_code}',
        'payment_id': payment_id,
        'section_code': section_code,
        'amount': float(amount),
        'payment_net_amount': payment.net_amount,
    }, 'TDS deduction recorded')


@router.get('/deductions')
def list_deductions(tenant_id: str = Depends(current_tenant),
                    from_date: str | None = Query(None),
                    to_date: str | None = Query(None),
                    db: Session = Depends(get_db)):
    """List all TDS deductions based on GL entries."""
    q = db.query(GLEntryModel).filter(
        GLEntryModel.tenant_id == tenant_id,
        GLEntryModel.voucher_type == 'tds_deduction'
    )
    if from_date:
        q = q.filter(GLEntryModel.posting_date >= from_date)
    if to_date:
        q = q.filter(GLEntryModel.posting_date <= to_date)

    deductions = []
    for entry in q.order_by(GLEntryModel.posting_date.desc()).all():
        deductions.append({
            'tds_id': entry.voucher_id,
            'amount': float(entry.credit),
            'party_id': entry.party_id,
            'posting_date': str(entry.posting_date),
            'remarks': entry.remarks,
        })

    total = sum(d['amount'] for d in deductions)
    return ok({'deductions': deductions, 'total_tds': total})


def _quarter_range(quarter: int, year: int) -> tuple[date, date]:
    """Return (start_date, end_date) for a given quarter and year."""
    quarters = {
        1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)
    }
    if quarter not in quarters:
        raise APIError('INVALID_QUARTER', 'Quarter must be 1-4', status_code=400)
    start_month, end_month = quarters[quarter]
    start = date(year, start_month, 1)
    import calendar
    end = date(year, end_month, calendar.monthrange(year, end_month)[1])
    return start, end


@router.get('/26q/compute/{quarter}/{year}')
def compute_26q(quarter: int, year: int,
                tenant_id: str = Depends(current_tenant),
                db: Session = Depends(get_db)):
    """Compute Form 26Q - TDS quarterly return."""
    from app.models.e2e import PartyModel

    start_date, end_date = _quarter_range(quarter, year)

    # Get all TDS deductions in the quarter
    tds_entries = db.query(GLEntryModel).filter(
        GLEntryModel.tenant_id == tenant_id,
        GLEntryModel.voucher_type == 'tds_deduction',
        GLEntryModel.posting_date >= start_date,
        GLEntryModel.posting_date <= end_date,
    ).all()

    # Aggregate by party (deductee)
    party_tds = {}
    for entry in tds_entries:
        party_id = entry.party_id
        if party_id not in party_tds:
            party = db.query(PartyModel).filter_by(
                tenant_id=tenant_id, party_id=party_id
            ).first()
            party_tds[party_id] = {
                'party_id': party_id,
                'pan': party.pan if party else 'N/A',
                'party_name': party.party_name if party else 'Unknown',
                'total_tds': Decimal('0'),
                'deductions': [],
            }
        party_tds[party_id]['total_tds'] += entry.credit
        party_tds[party_id]['deductions'].append({
            'tds_id': entry.voucher_id,
            'amount': float(entry.credit),
            'date': str(entry.posting_date),
        })

    # Form 26Q structure
    total_tds = sum(p['total_tds'] for p in party_tds.values())

    return ok({
        'form': '26Q',
        'quarter': quarter,
        'year': year,
        'period': f'{start_date.isoformat()} to {end_date.isoformat()}',
        'summary': {
            'total_deductees': len(party_tds),
            'total_tds_amount': float(total_tds),
        },
        'deductees': list(party_tds.values()),
        'status': 'Computed - Ready for filing',
    })


@router.get('/26q/json/{quarter}')
def get_26q_json(quarter: int, year: int = None,
                 tenant_id: str = Depends(current_tenant),
                 db: Session = Depends(get_db)):
    """Get 26Q JSON in TRACES-compatible format."""
    if year is None:
        year = date.today().year

    start_date, end_date = _quarter_range(quarter, year)

    # Get TDS entries
    tds_entries = db.query(GLEntryModel).filter(
        GLEntryModel.tenant_id == tenant_id,
        GLEntryModel.voucher_type == 'tds_deduction',
        GLEntryModel.posting_date >= start_date,
        GLEntryModel.posting_date <= end_date,
    ).all()

    # Get deductee details
    from app.models.e2e import PartyModel
    deductees = {}
    for entry in tds_entries:
        if entry.party_id not in deductees:
            party = db.query(PartyModel).filter_by(
                tenant_id=tenant_id, party_id=entry.party_id
            ).first()
            deductees[entry.party_id] = {
                'deducteeId': entry.party_id,
                'pan': party.pan if party else '',
                'name': party.party_name if party else '',
                'tdsEntries': [],
            }
        deductees[entry.party_id]['tdsEntries'].append({
            'dateOfDeduction': entry.posting_date.isoformat(),
            'amount': str(entry.credit),
            'sectionCode': entry.remarks.split()[-1] if entry.remarks else '194',
        })

    json_payload = {
        'quarter': str(quarter),
        'form': '26Q',
        'assessmentYear': f'{year}-{year+1}',
        'deductees': list(deductees.values()),
    }

    return ok(json_payload, '26Q JSON generated')


@router.get('/certificates/{party_id}')
def tds_certificate(party_id: str,
                    tenant_id: str = Depends(current_tenant),
                    db: Session = Depends(get_db)):
    """Get TDS certificate summary for a party."""
    from app.models.e2e import PartyModel

    party = db.query(PartyModel).filter_by(
        tenant_id=tenant_id, party_id=party_id
    ).first()
    if not party:
        raise APIError('PARTY_NOT_FOUND', f'Party {party_id} not found', status_code=404)

    tds_entries = db.query(GLEntryModel).filter(
        GLEntryModel.tenant_id == tenant_id,
        GLEntryModel.voucher_type == 'tds_deduction',
        GLEntryModel.party_id == party_id,
    ).all()

    total_tds = sum(e.credit for e in tds_entries)
    certificates = [{
        'certificate_no': f'TDS-CERT-{party_id}-{e.posting_date.year}',
        'period': str(e.posting_date.year),
        'amount': float(e.credit),
        'status': 'Issued',
    } for e in tds_entries]

    return ok({
        'party_id': party_id,
        'party_name': party.party_name,
        'pan': party.pan,
        'total_tds_deducted': float(total_tds),
        'certificates': certificates,
    })


@router.post('/certificates/generate')
def generate_tds_certificate(payload: dict,
                             tenant_id: str = Depends(current_tenant),
                             db: Session = Depends(get_db)):
    """Generate a consolidated TDS certificate for a party and period."""
    party_id = payload.get('party_id')
    year = payload.get('year', date.today().year)

    if not party_id:
        raise APIError('MISSING_PARTY', 'party_id is required', status_code=400)

    from app.models.e2e import PartyModel
    party = db.query(PartyModel).filter_by(
        tenant_id=tenant_id, party_id=party_id
    ).first()
    if not party:
        raise APIError('PARTY_NOT_FOUND', f'Party {party_id} not found', status_code=404)

    tds_entries = db.query(GLEntryModel).filter(
        GLEntryModel.tenant_id == tenant_id,
        GLEntryModel.voucher_type == 'tds_deduction',
        GLEntryModel.party_id == party_id,
        func.extract('year', GLEntryModel.posting_date) == year,
    ).all()

    total_tds = sum(e.credit for e in tds_entries)
    if total_tds == 0:
        raise APIError('NO_TDS_DATA', 'No TDS deductions found for the specified period', status_code=404)

    certificate_no = f'TDS-{party_id[:8].upper()}-{year}'

    # Audit log
    audit = AuditLog(db)
    audit.log(tenant_id, 'system', 'TDS_CERTIFICATE_GENERATED', 'tds_certificate', certificate_no,
              {'party_id': party_id, 'year': year, 'total_tds': float(total_tds)})

    return ok({
        'certificate_no': certificate_no,
        'party_id': party_id,
        'party_name': party.party_name,
        'pan': party.pan,
        'year': year,
        'total_tds': float(total_tds),
        'status': 'Generated',
        'entries_count': len(tds_entries),
    }, 'TDS certificate generated')


@router.get('/payable')
def tds_payable(tenant_id: str = Depends(current_tenant),
                db: Session = Depends(get_db)):
    """Get total TDS payable summary."""
    tds_entries = db.query(GLEntryModel).filter(
        GLEntryModel.tenant_id == tenant_id,
        GLEntryModel.account == 'TDS Payable',
    ).all()

    total_payable = sum(e.credit for e in tds_entries)

    # Group by party
    party_wise = {}
    for entry in tds_entries:
        if entry.party_id not in party_wise:
            party_wise[entry.party_id] = Decimal('0')
        party_wise[entry.party_id] += entry.credit

    return ok({
        'total_tds_payable': float(total_payable),
        'party_wise': {pid: float(amt) for pid, amt in party_wise.items()},
        'entries_count': len(tds_entries),
    })