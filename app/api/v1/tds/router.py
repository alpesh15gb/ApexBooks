from fastapi import APIRouter, Depends
from app.api.v1.deps import current_tenant
from app.core.exceptions import ok
from app.services.repository import repo
router=APIRouter(prefix='/tds', tags=['TDS'])

@router.get('/sections')
def route_0(tenant_id: str = Depends(current_tenant)): return ok({'path':'/tds/sections','data':[]})

@router.post('/deductions')
def route_1(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/tds/deductions','payload':payload or {}}, 'Accepted')

@router.get('/deductions')
def route_2(tenant_id: str = Depends(current_tenant)): return ok({'path':'/tds/deductions','data':[]})

@router.get('/26q/compute/{quarter}/{year}')
def route_3(quarter: int, year: int, tenant_id: str = Depends(current_tenant)): return ok({'path':'/tds/26q/compute/{quarter}/{year}','data':[]})

@router.get('/26q/json/{quarter}')
def route_4(quarter: int, tenant_id: str = Depends(current_tenant)): return ok({'path':'/tds/26q/json/{quarter}','data':[]})

@router.get('/certificates/{party_id}')
def route_5(party_id: str, tenant_id: str = Depends(current_tenant)): return ok({'path':'/tds/certificates/{party_id}','data':[]})

@router.post('/certificates/generate')
def route_6(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/tds/certificates/generate','payload':payload or {}}, 'Accepted')

@router.get('/payable')
def route_7(tenant_id: str = Depends(current_tenant)): return ok({'path':'/tds/payable','data':[]})
