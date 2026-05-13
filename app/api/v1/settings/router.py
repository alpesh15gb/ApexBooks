from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.v1.deps import current_tenant
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.services.settings_service import settings_service, _default_settings

router = APIRouter(prefix='/settings', tags=['Settings'])

@router.get('/categories')
def list_categories(tenant_id: str = Depends(current_tenant)):
    return ok({'categories': list(_default_settings().keys())})

@router.get('/{category}')
def get_settings_category(category: str, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    return ok(settings_service.get_category(db, tenant_id, category))

@router.put('/{category}')
def update_settings_category(category: str, payload: dict, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    return ok(settings_service.update_category(db, tenant_id, category, payload))

@router.get('/')
def get_all_settings(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    return ok(settings_service.get_settings(db, tenant_id))

@router.put('/')
def update_bulk_settings(payload: dict, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    return ok(settings_service.update_bulk(db, tenant_id, payload))

@router.get('/gst/enabled')
def gst_enabled(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    return ok({'enabled': settings_service.is_gst_enabled(db, tenant_id)})

@router.get('/einvoice/enabled')
def einvoice_enabled(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    return ok({'enabled': settings_service.is_einvoice_enabled(db, tenant_id)})

@router.get('/ewaybill/enabled')
def ewaybill_enabled(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    return ok({'enabled': settings_service.is_ewaybill_enabled(db, tenant_id)})

@router.get('/invoice-numbering')
def invoice_numbering(kind: str = 'sales', tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    return ok(settings_service.get_invoice_numbering(db, tenant_id, kind))
