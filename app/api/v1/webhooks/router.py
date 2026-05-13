from fastapi import APIRouter, Depends
from app.api.v1.deps import current_tenant
from app.core.exceptions import ok
from app.services.repository import repo
router=APIRouter(prefix='/webhooks', tags=['Webhooks'])

@router.post('/')
def route_0(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/webhooks/','payload':payload or {}}, 'Accepted')

@router.get('/')
def route_1(tenant_id: str = Depends(current_tenant)): return ok({'path':'/webhooks/','data':[]})

@router.delete('/{row_id}')
def route_2(row_id: str, tenant_id: str = Depends(current_tenant)): return ok(message='Deleted')

@router.get('/events')
def route_3(tenant_id: str = Depends(current_tenant)): return ok({'path':'/webhooks/events','data':[]})

@router.get('/logs')
def route_4(tenant_id: str = Depends(current_tenant)): return ok({'path':'/webhooks/logs','data':[]})
