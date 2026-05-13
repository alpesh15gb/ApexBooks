from fastapi import APIRouter, Depends
from app.api.v1.deps import current_tenant
from app.core.exceptions import ok
from app.services.repository import repo
router=APIRouter(prefix='/bank', tags=['Banking'])

@router.post('/accounts')
def route_0(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/bank/accounts','payload':payload or {}}, 'Accepted')

@router.get('/accounts')
def route_1(tenant_id: str = Depends(current_tenant)): return ok({'path':'/bank/accounts','data':[]})

@router.post('/transactions/import')
def route_2(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/bank/transactions/import','payload':payload or {}}, 'Accepted')

@router.get('/transactions')
def route_3(tenant_id: str = Depends(current_tenant)): return ok({'path':'/bank/transactions','data':[]})

@router.post('/reconcile')
def route_4(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/bank/reconcile','payload':payload or {}}, 'Accepted')

@router.get('/unreconciled')
def route_5(tenant_id: str = Depends(current_tenant)): return ok({'path':'/bank/unreconciled','data':[]})

@router.post('/transactions/{row_id}/match')
def route_6(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/bank/transactions/{row_id}/match','payload':payload or {}}, 'Accepted')
