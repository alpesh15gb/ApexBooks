from fastapi import APIRouter, Depends
from app.api.v1.deps import current_tenant
from app.core.exceptions import ok
from app.services.repository import repo
router=APIRouter(prefix='/admin', tags=['Admin'])

@router.get('/tenants')
def route_0(tenant_id: str = Depends(current_tenant)): return ok({'path':'/admin/tenants','data':[]})

@router.get('/tenants/{tenant_id}')
def route_1(tenant_id_path: str, tenant_id: str = Depends(current_tenant)): return ok({'path':'/admin/tenants/{tenant_id}','data':[]})

@router.post('/tenants/{tenant_id}/schemas')
def route_2(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/admin/tenants/{tenant_id}/schemas','payload':payload or {}}, 'Accepted')

@router.get('/health')
def route_3(tenant_id: str = Depends(current_tenant)): return ok({'path':'/admin/health','data':[]})
