from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.exceptions import ok
from app.core.security import current_principal
from app.services.normalized_repository import normalized_repo, model_dict

router=APIRouter(prefix='/items', tags=['Items'])

@router.post('')
def create(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.create_item(db, principal['tenant_id'], payload), 'Item created')

@router.get('')
def list_rows(search: str | None = None, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.list_items(db, principal['tenant_id'], search))

@router.post('/import')
def bulk_import(payload: list[dict], principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok([normalized_repo.create_item(db, principal['tenant_id'], row) for row in payload], 'Bulk import completed')

@router.get('/export')
def export(principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.list_items(db, principal['tenant_id']))

@router.post('/price-list')
def price_list(payload: dict):
    return ok({'accepted': True, 'payload': payload})

@router.get('/{row_id}/price-list')
def get_price_list(row_id: str):
    return ok([])

@router.get('/{row_id}')
def get(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(model_dict(normalized_repo.get_item(db, principal['tenant_id'], row_id)))

@router.put('/{row_id}')
def update(row_id: str, payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.update_item(db, principal['tenant_id'], row_id, payload), 'Item updated')

@router.delete('/{row_id}')
def delete(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec=normalized_repo.get_item(db, principal['tenant_id'], row_id); rec.is_deleted=True; return ok(message='Item soft deleted')
