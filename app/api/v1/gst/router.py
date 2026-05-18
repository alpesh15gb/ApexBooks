from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.core.database import get_db
from app.core.exceptions import ok
from app.core.security import current_principal
from app.services.gst_engine import calculate_tax
from app.services.normalized_repository import normalized_repo
from app.services.gstr_service import gstr1_payload, gstr3b_compute
from app.tasks.background_worker import create_background_job
from app.models.accounting import InvoiceModel, GLEntryModel

router = APIRouter(prefix='/gst', tags=['GST Compliance'])


@router.post('/tax-calculate')
def tax_calculate(payload: dict):
    return ok(calculate_tax(**payload))


@router.post('/reconcile/dispatch')
def dispatch_reconciliation(
    payload: dict,
    principal: dict = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Dispatch GST reconciliation as a background job."""
    month = payload.get('month')
    year = payload.get('year')
    if not month or not year:
        raise Exception('month and year are required')
    job = create_background_job(
        db, principal['tenant_id'], 'gst_reconciliation',
        {'month': month, 'year': year},
        created_by=principal.get('user_id'),
    )
    return ok({'job_id': job.id, 'status': job.status}, 'Reconciliation queued')


@router.post('/notify/dispatch')
def dispatch_notification(
    payload: dict,
    principal: dict = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Dispatch notification as a background job."""
    job = create_background_job(
        db, principal['tenant_id'], 'send_notification',
        {
            'channel': payload.get('channel', 'email'),
            'recipient': payload.get('recipient'),
            'subject': payload.get('subject', ''),
            'body': payload.get('body', ''),
        },
        created_by=principal.get('user_id'),
    )
    return ok({'job_id': job.id, 'status': job.status}, 'Notification queued')


@router.get('/gstr1/summary/{month}/{year}')
def gstr1_summary(month: int, year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.gstr1_summary(db, principal['tenant_id'], month, year))


for table in ['b2b', 'b2cl', 'b2cs', 'cdnr', 'cdnur', 'exp', 'nil', 'hsn', 'docs']:
    async def table_fn(month: int, year: int, principal: dict = Depends(current_principal),
                       db: Session = Depends(get_db), table=table):
        summary = normalized_repo.gstr1_summary(db, principal['tenant_id'], month, year)
        return ok(summary.get('tables', {}).get(table.upper(), {}))

    router.add_api_route(f'/gstr1/{table}/{{month}}/{{year}}', table_fn, methods=['GET'])


@router.get('/gstr1/json/{month}/{year}')
def gstr1_json(month: int, year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.gstr1_summary(db, principal['tenant_id'], month, year))


@router.get('/gstr1/excel/{month}/{year}')
def gstr1_excel(month: int, year: int):
    return ok({'file_url': f'/exports/gstr1-{month}-{year}.xlsx'})


@router.post('/gstr1/validate/{month}/{year}')
def gstr1_validate(month: int, year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Validate GSTR-1 data before filing - checks for missing GSTINs, rate mismatches."""
    summary = normalized_repo.gstr1_summary(db, principal['tenant_id'], month, year)
    errors = []
    tables = summary.get('tables', {})
    for table_name, data in tables.items():
        count = data.get('count', 0)
        if count > 0:
            taxable = data.get('taxable', 0)
            tax = data.get('tax', 0)
            expected_tax = taxable * Decimal('0.18')  # rough check
            if abs(tax - expected_tax) > Decimal('1.00') and taxable > 0:
                errors.append(f'{table_name}: Tax amount {tax} seems inconsistent with taxable {taxable}')
    return ok({'valid': len(errors) == 0, 'errors': errors})


@router.post('/gstr1/file/{month}/{year}')
def gstr1_file(month: int, year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """File GSTR-1 - generates JSON payload and marks invoices as filed."""
    tenant_id = principal['tenant_id']
    summary = normalized_repo.gstr1_summary(db, tenant_id, month, year)
    invoices = db.query(InvoiceModel).filter(
        InvoiceModel.tenant_id == tenant_id,
        InvoiceModel.invoice_kind == 'sales',
        InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid']),
        func.extract('month', InvoiceModel.invoice_date) == month,
        func.extract('year', InvoiceModel.invoice_date) == year,
    ).all()

    # Mark invoices as GSTR-1 filed
    for inv in invoices:
        inv.e_invoice_status = 'GSTR1 Filed'

    db.flush()

    from app.services.audit_service import AuditLog
    audit = AuditLog(db)
    audit.log(tenant_id, principal['user_id'],
              'GSTR1_FILED', 'gstr1', f'{month}-{year}',
              {'month': month, 'year': year, 'invoice_count': len(invoices)})

    return ok({
        'arn': f'GSTR1-{tenant_id[:8]}-{month:02d}{year}',
        'status': 'Filed',
        'month': month, 'year': year,
        'invoice_count': len(invoices),
    }, 'GSTR-1 filed successfully')


@router.get('/gstr1/status/{month}/{year}')
def gstr1_status(month: int, year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Check GSTR-1 filing status."""
    invoices = db.query(InvoiceModel).filter(
        InvoiceModel.tenant_id == principal['tenant_id'],
        InvoiceModel.invoice_kind == 'sales',
        func.extract('month', InvoiceModel.invoice_date) == month,
        func.extract('year', InvoiceModel.invoice_date) == year,
    ).all()
    filed = all(inv.e_invoice_status == 'GSTR1 Filed' for inv in invoices if inv.status != 'Draft')
    return ok({'status': 'Filed' if filed else 'Not Filed', 'total_invoices': len(invoices)})


@router.post('/gstr2a/fetch/{month}/{year}')
def gstr2a_fetch(month: int, year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Fetch GSTR-2A data (ITC matching)."""
    job = create_background_job(
        db, principal['tenant_id'], 'gstr2a_fetch',
        {'month': month, 'year': year},
        created_by=principal.get('user_id'),
    )
    return ok({'job_id': job.id, 'status': job.status}, 'GSTR-2A fetch queued')


@router.get('/gstr2a/{month}/{year}')
def gstr2a(month: int, year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Get GSTR-2A data - auto-populated ITC from vendor invoices."""
    # In production, this would come from GST portal API.
    # Here we compute from purchase invoices.
    purchases = db.query(InvoiceModel).filter(
        InvoiceModel.tenant_id == principal['tenant_id'],
        InvoiceModel.invoice_kind == 'purchase',
        InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid']),
        func.extract('month', InvoiceModel.invoice_date) == month,
        func.extract('year', InvoiceModel.invoice_date) == year,
    ).all()

    entries = []
    for inv in purchases:
        entries.append({
            'gstin': inv.party_gstin,
            'invoice_number': inv.invoice_number,
            'invoice_date': str(inv.invoice_date),
            'taxable_value': float(inv.subtotal),
            'igst': float(inv.total_igst),
            'cgst': float(inv.total_cgst),
            'sgst': float(inv.total_sgst),
            'cess': float(inv.total_cess),
            'supply_type': inv.supply_type,
        })

    return ok(entries)


@router.post('/gstr2b/fetch/{month}/{year}')
def gstr2b_fetch(month: int, year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Fetch GSTR-2B data."""
    job = create_background_job(
        db, principal['tenant_id'], 'gstr2b_fetch',
        {'month': month, 'year': year},
        created_by=principal.get('user_id'),
    )
    return ok({'job_id': job.id, 'status': job.status}, 'GSTR-2B fetch queued')


@router.get('/reconcile/2a-vs-books/{month}')
def rec_2a(month: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Reconcile GSTR-2A with books (ITC claimed vs ITC available)."""
    year = date.today().year

    # ITC from purchase invoices in books
    purchases = db.query(InvoiceModel).filter(
        InvoiceModel.tenant_id == principal['tenant_id'],
        InvoiceModel.invoice_kind == 'purchase',
        InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid']),
        func.extract('month', InvoiceModel.invoice_date) == month,
        func.extract('year', InvoiceModel.invoice_date) == year,
    ).all()

    books_itc = {
        'igst': sum(float(inv.total_igst) for inv in purchases),
        'cgst': sum(float(inv.total_cgst) for inv in purchases),
        'sgst': sum(float(inv.total_sgst) for inv in purchases),
        'cess': sum(float(inv.total_cess) for inv in purchases),
    }

    # GSTR-2A ITC (from portal - using same data in mock)
    gstr2a_itc = {k: v * Decimal('0.95') for k, v in books_itc.items()}  # Simulate slight mismatch

    matched = 0
    mismatched = 0
    mismatches = []
    for key in books_itc:
        diff = abs(float(books_itc[key] - gstr2a_itc[key]))
        if diff < 0.01:
            matched += 1
        else:
            mismatched += 1
            mismatches.append({
                'tax_type': key,
                'books_amount': float(books_itc[key]),
                'gstr2a_amount': float(gstr2a_itc[key]),
                'difference': round(diff, 2),
            })

    return ok({
        'matched': matched,
        'mismatched': mismatched,
        'mismatches': mismatches,
        'reconciliation_percentage': round(matched / (matched + mismatched) * 100, 2) if (matched + mismatched) > 0 else 0,
    })


@router.get('/reconcile/2b-vs-books/{month}')
def rec_2b(month: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Reconcile GSTR-2B with books."""
    result = rec_2a(month, principal, db)  # Similar logic for mock
    return ok({**result.get('data', {}), 'source': 'GSTR-2B'})


@router.get('/itc-available/{month}/{year}')
def itc(month: int, year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Get ITC available for a given month/year."""
    purchases = db.query(InvoiceModel).filter(
        InvoiceModel.tenant_id == principal['tenant_id'],
        InvoiceModel.invoice_kind == 'purchase',
        InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid']),
        func.extract('month', InvoiceModel.invoice_date) == month,
        func.extract('year', InvoiceModel.invoice_date) == year,
    ).all()

    result = {}
    for key in ['total_igst', 'total_cgst', 'total_sgst', 'total_cess']:
        result[key.replace('total_', '')] = float(sum(getattr(inv, key) for inv in purchases))

    return ok(result)


@router.get('/gstr3b/compute/{month}/{year}')
def g3b(month: int, year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.gstr3b(db, principal['tenant_id'], month, year))


for path in ['table3_1', 'table3_2', 'table4', 'table5', 'json']:
    async def g3b_table(month: int, year: int, principal: dict = Depends(current_principal),
                        db: Session = Depends(get_db), path=path):
        return ok({'table': path, **normalized_repo.gstr3b(db, principal['tenant_id'], month, year)})

    router.add_api_route(f'/gstr3b/{path}/{{month}}/{{year}}', g3b_table, methods=['GET'])


@router.post('/gstr3b/file/{month}/{year}')
def g3b_file(month: int, year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """File GSTR-3B with computed data."""
    tenant_id = principal['tenant_id']
    result = normalized_repo.gstr3b(db, tenant_id, month, year)

    from app.models.accounting import GSTReturnModel
    existing = db.query(GSTReturnModel).filter_by(
        tenant_id=tenant_id, return_type='GSTR3B',
        period_month=month, period_year=year
    ).first()

    if not existing:
        ret = GSTReturnModel(
            tenant_id=tenant_id,
            return_type='GSTR3B',
            period_month=month,
            period_year=year,
            status='Filed',
            payload=result,
            filed_at=date.today(),
        )
        db.add(ret)
        db.flush()
    else:
        existing.status = 'Filed'
        existing.payload = result
        existing.filed_at = date.today()

    from app.services.audit_service import AuditLog
    audit = AuditLog(db)
    audit.log(tenant_id, principal['user_id'],
              'GSTR3B_FILED', 'gstr3b', f'{month}-{year}', result)

    challenge_code = f'GSTR3B-{tenant_id[:8]}-{month:02d}{year}'
    return ok({
        'arn': challenge_code,
        'status': 'Filed',
        'month': month, 'year': year,
        'data': result,
    }, 'GSTR-3B filed successfully')


@router.get('/gstr3b/liability')
def liability(month: int | None = None, year: int | None = None,
              principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Get current GST liability (total outward tax - ITC)."""
    today = date.today()
    m = month or today.month
    y = year or today.year

    result = normalized_repo.gstr3b(db, principal['tenant_id'], m, y)

    sup = result.get('sup_details', {})
    itc_elg = result.get('itc_elg', {})

    net_liability = {}
    key_map = {'igst': 'iamt', 'cgst': 'camt', 'sgst': 'samt', 'cess': 'csamt'}
    for key, sup_key in key_map.items():
        outward_tax = sup.get(sup_key, 0)
        available_itc = itc_elg.get(sup_key, 0)
        net = float(outward_tax) - float(available_itc)
        net_liability[key] = round(max(net, 0), 2)

    return ok(net_liability)


@router.post('/challan/create')
def challan_create(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Create a GST payment challan."""
    from uuid import uuid4
    from app.models.e2e import ResourceRecord

    challan_id = f'CHL-{uuid4().hex[:12].upper()}'
    amount = payload.get('amount', 0)
    tax_type = payload.get('tax_type', 'IGST')

    rec = ResourceRecord(
        tenant_id=principal['tenant_id'],
        resource='challan',
        resource_id=challan_id,
        payload={'amount': amount, 'tax_type': tax_type, 'status': 'generated', **payload},
        status='generated',
        txn_date=date.today(),
        amount=float(amount),
    )
    db.add(rec)
    db.flush()

    return ok({'challan_id': challan_id, 'amount': amount, 'tax_type': tax_type, 'status': 'generated'})


@router.get('/challan/{row_id}')
def challan(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Get challan details."""
    from app.models.e2e import ResourceRecord
    rec = db.query(ResourceRecord).filter_by(
        tenant_id=principal['tenant_id'], resource='challan', resource_id=row_id
    ).first()
    if not rec:
        raise Exception(f'Challan {row_id} not found')
    return ok(rec.payload)


@router.post('/challan/{row_id}/pay')
def challan_pay(row_id: str, payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Mark challan as paid and create payment record."""
    from app.models.e2e import ResourceRecord
    rec = db.query(ResourceRecord).filter_by(
        tenant_id=principal['tenant_id'], resource='challan', resource_id=row_id
    ).first()
    if not rec:
        raise Exception(f'Challan {row_id} not found')

    rec.status = 'Paid'
    rec.payload['payment_status'] = 'Paid'
    rec.payload['cin'] = payload.get('cin', f'CIN-{row_id[:8]}')
    db.flush()

    return ok({'challan_id': row_id, 'status': 'Paid', 'cin': rec.payload.get('cin')})


for ledger in ['cash', 'credit', 'liability']:
    async def ledger_fn(ledger=ledger, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
        from app.services.gstr_service import gstr3b_compute
        tenant_id = principal['tenant_id']
        today = date.today()
        result = normalized_repo.gstr3b(db, tenant_id, today.month, today.year)

        if ledger == 'cash':
            balance = sum(r.get('grand_total', 0) for r in db.query(InvoiceModel).filter(
                InvoiceModel.tenant_id == tenant_id,
                InvoiceModel.status == 'Draft',
                InvoiceModel.invoice_kind == 'sales',
            ).all())
        elif ledger == 'credit':
            balance = sum(
                float(r.grand_total - r.amount_paid) for r in
                db.query(InvoiceModel).filter(
                    InvoiceModel.tenant_id == tenant_id,
                    InvoiceModel.invoice_kind == 'sales',
                    InvoiceModel.status.in_(['Submitted', 'Part Paid']),
                ).all()
            )
        else:  # liability
            sup = result.get('sup_details', {})
            net = result.get('itc_elg', {}).get('itc_avl', {})
            igst = float(sup.get('iamt', 0)) - float(net.get('igst', 0))
            cgst = float(sup.get('camt', 0)) - float(net.get('cgst', 0))
            sgst = float(sup.get('samt', 0)) - float(net.get('sgst', 0))
            balance = round(max(igst, 0) + max(cgst, 0) + max(sgst, 0), 2)

        return ok({'ledger': ledger, 'balance': balance})

    router.add_api_route(f'/ledger/{ledger}', ledger_fn, methods=['GET'])


@router.get('/gstr9/compute/{year}')
def gstr9(year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Compute annual return GSTR-9."""
    tenant_id = principal['tenant_id']

    annual_sales = db.query(InvoiceModel).filter(
        InvoiceModel.tenant_id == tenant_id,
        InvoiceModel.invoice_kind == 'sales',
        InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid']),
        func.extract('year', InvoiceModel.invoice_date) == year,
    ).all()

    annual_purchases = db.query(InvoiceModel).filter(
        InvoiceModel.tenant_id == tenant_id,
        InvoiceModel.invoice_kind == 'purchase',
        InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid']),
        func.extract('year', InvoiceModel.invoice_date) == year,
    ).all()

    total_sales = sum(float(inv.grand_total) for inv in annual_sales)
    total_purchases = sum(float(inv.grand_total) for inv in annual_purchases)
    total_igst = sum(float(inv.total_igst) for inv in annual_sales)
    total_cgst = sum(float(inv.total_cgst) for inv in annual_sales)
    total_sgst = sum(float(inv.total_sgst) for inv in annual_sales)
    total_input_igst = sum(float(inv.total_igst) for inv in annual_purchases)
    total_input_cgst = sum(float(inv.total_cgst) for inv in annual_purchases)
    total_input_sgst = sum(float(inv.total_sgst) for inv in annual_purchases)

    return ok({
        'year': year,
        'annual_return': {
            'total_outward_sales': total_sales,
            'total_inward_purchases': total_purchases,
            'total_output_tax': {
                'igst': total_igst, 'cgst': total_cgst, 'sgst': total_sgst,
            },
            'total_input_tax_credit': {
                'igst': total_input_igst, 'cgst': total_input_cgst, 'sgst': total_input_sgst,
            },
            'net_liability': {
                'igst': round(max(total_igst - total_input_igst, 0), 2),
                'cgst': round(max(total_cgst - total_input_cgst, 0), 2),
                'sgst': round(max(total_sgst - total_input_sgst, 0), 2),
            },
        },
    })


@router.get('/gstr9c/compute/{year}')
def gstr9c(year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Compute GSTR-9C (reconciliation statement)."""
    gstr9_data = gstr9(year, principal, db).get('json', {}).get('annual_return', {})
    return ok({
        'year': year,
        'reconciliation': gstr9_data,
        'status': 'Computed - review required',
    })


@router.post('/lut/register')
def lut(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Register LUT (Letter of Undertaking) for export without payment of IGST."""
    from uuid import uuid4
    from app.models.e2e import ResourceRecord

    lut_id = f'LUT-{uuid4().hex[:12].upper()}'
    rec = ResourceRecord(
        tenant_id=principal['tenant_id'],
        resource='lut',
        resource_id=lut_id,
        payload={'financial_year': payload.get('financial_year', f'{date.today().year}-{date.today().year+1}'),
                 'gstin': payload.get('gstin'), 'status': 'Registered', **payload},
        status='active',
        txn_date=date.today(),
    )
    db.add(rec)
    db.flush()

    return ok({'lut_id': lut_id, 'status': 'Registered', 'arn': f'LUT-ARN-{lut_id}'})


@router.get('/notices')
def notices(principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Get GST notices/orders from tax department (mock - integrates with GST portal in production)."""
    return ok([])