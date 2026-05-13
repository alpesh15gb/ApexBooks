from fastapi import APIRouter, Depends
from app.api.v1.deps import current_tenant
from app.core.exceptions import ok
from app.services.repository import repo
router=APIRouter(prefix='/accounts', tags=['Accounts'])

@router.post('/coa')
def route_0(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/coa','payload':payload or {}}, 'Accepted')

@router.get('/coa')
def route_1(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/coa','data':[]})

@router.get('/coa/{row_id}')
def route_2(row_id: str, tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/coa/{row_id}','data':[]})

@router.put('/coa/{row_id}')
def route_3(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/coa/{row_id}','payload':payload or {}}, 'Accepted')

@router.delete('/coa/{row_id}')
def route_4(row_id: str, tenant_id: str = Depends(current_tenant)): return ok(message='Deleted')

@router.post('/coa/import')
def route_5(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/coa/import','payload':payload or {}}, 'Accepted')

@router.post('/journal')
def route_6(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/journal','payload':payload or {}}, 'Accepted')

@router.get('/journal')
def route_7(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/journal','data':[]})

@router.get('/journal/{row_id}')
def route_8(row_id: str, tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/journal/{row_id}','data':[]})

@router.put('/journal/{row_id}')
def route_9(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/journal/{row_id}','payload':payload or {}}, 'Accepted')

@router.post('/journal/{row_id}/submit')
def route_10(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/journal/{row_id}/submit','payload':payload or {}}, 'Accepted')

@router.post('/journal/{row_id}/reverse')
def route_11(payload: dict | None = None, tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/journal/{row_id}/reverse','payload':payload or {}}, 'Accepted')

@router.get('/journal/templates')
def route_12(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/journal/templates','data':[]})

@router.get('/reports/trial-balance')
def route_13(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/reports/trial-balance','data':[]})

@router.get('/reports/balance-sheet')
def route_14(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/reports/balance-sheet','data':[]})

@router.get('/reports/profit-loss')
def route_15(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/reports/profit-loss','data':[]})

@router.get('/reports/cash-flow')
def route_16(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/reports/cash-flow','data':[]})

@router.get('/reports/general-ledger')
def route_17(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/reports/general-ledger','data':[]})

@router.get('/reports/party-ledger/{party_id}')
def route_18(party_id: str, tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/reports/party-ledger/{party_id}','data':[]})

@router.get('/reports/daybook')
def route_19(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/reports/daybook','data':[]})

@router.get('/reports/bank-reconciliation')
def route_20(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/reports/bank-reconciliation','data':[]})

@router.get('/reports/accounts-receivable')
def route_21(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/reports/accounts-receivable','data':[]})

@router.get('/reports/accounts-payable')
def route_22(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/reports/accounts-payable','data':[]})

@router.get('/reports/stock-summary')
def route_23(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/reports/stock-summary','data':[]})

@router.get('/reports/gst-payable')
def route_24(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/reports/gst-payable','data':[]})

@router.get('/reports/tds-summary')
def route_25(tenant_id: str = Depends(current_tenant)): return ok({'path':'/accounts/reports/tds-summary','data':[]})
