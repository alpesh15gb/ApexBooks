from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.exceptions import ok
from app.core.security import current_principal
from app.services.gst_engine import calculate_tax
from app.services.normalized_repository import normalized_repo
from app.tasks.background_worker import create_background_job

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
def gstr1_validate(month: int, year: int):
    return ok({'valid': True, 'errors': []})


@router.post('/gstr1/file/{month}/{year}')
def gstr1_file(month: int, year: int):
    return ok({'arn': 'mock-arn', 'status': 'filed'})


@router.get('/gstr1/status/{month}/{year}')
def gstr1_status(month: int, year: int):
    return ok({'status': 'Not Filed'})


@router.post('/gstr2a/fetch/{month}/{year}')
def gstr2a_fetch(month: int, year: int):
    return ok({'job_id': 'fetch-2a', 'status': 'queued'})


@router.get('/gstr2a/{month}/{year}')
def gstr2a(month: int, year: int):
    return ok([])


@router.post('/gstr2b/fetch/{month}/{year}')
def gstr2b_fetch(month: int, year: int):
    return ok({'job_id': 'fetch-2b', 'status': 'queued'})


@router.get('/reconcile/2a-vs-books/{month}')
def rec_2a(month: int):
    return ok({'matched': 0, 'mismatched': 0})


@router.get('/reconcile/2b-vs-books/{month}')
def rec_2b(month: int):
    return ok({'matched': 0, 'mismatched': 0})


@router.get('/itc-available/{month}/{year}')
def itc(month: int, year: int):
    return ok({'igst': 0, 'cgst': 0, 'sgst': 0, 'cess': 0})


@router.get('/gstr3b/compute/{month}/{year}')
def g3b(month: int, year: int, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.gstr3b(db, principal['tenant_id'], month, year))


for path in ['table3_1', 'table3_2', 'table4', 'table5', 'json']:
    async def g3b_table(month: int, year: int, principal: dict = Depends(current_principal),
                        db: Session = Depends(get_db), path=path):
        return ok({'table': path, **normalized_repo.gstr3b(db, principal['tenant_id'], month, year)})

    router.add_api_route(f'/gstr3b/{path}/{{month}}/{{year}}', g3b_table, methods=['GET'])


@router.post('/gstr3b/file/{month}/{year}')
def g3b_file(month: int, year: int):
    return ok({'status': 'filed'})


@router.get('/gstr3b/liability')
def liability():
    return ok({'igst': 0, 'cgst': 0, 'sgst': 0, 'cess': 0})


@router.post('/challan/create')
def challan_create(payload: dict):
    return ok({'challan_id': 'mock', **payload})


@router.get('/challan/{row_id}')
def challan(row_id: str):
    return ok({'challan_id': row_id})


@router.post('/challan/{row_id}/pay')
def challan_pay(row_id: str, payload: dict):
    return ok({'challan_id': row_id, 'status': 'Paid', 'cin': payload.get('cin')})


for ledger in ['cash', 'credit', 'liability']:
    async def ledger_fn(ledger=ledger):
        return ok({'ledger': ledger, 'balance': 0})

    router.add_api_route(f'/ledger/{ledger}', ledger_fn, methods=['GET'])


@router.get('/gstr9/compute/{year}')
def gstr9(year: int):
    return ok({'year': year, 'annual_return': {}})


@router.get('/gstr9c/compute/{year}')
def gstr9c(year: int):
    return ok({'year': year, 'reconciliation': {}})


@router.post('/lut/register')
def lut(payload: dict):
    return ok({'status': 'registered', 'arn': 'mock-lut'})


@router.get('/notices')
def notices():
    return ok([])