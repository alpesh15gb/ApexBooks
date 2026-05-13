from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.exceptions import ok
from app.core.security import current_principal
from app.services.normalized_repository import normalized_repo, model_dict

router=APIRouter(prefix='/parties', tags=['Parties'])

@router.post('')
def create(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.create_party(db, principal['tenant_id'], payload), 'Party created')

@router.get('')
def list_rows(search: str | None = None, type: str | None = None, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.list_parties(db, principal['tenant_id'], search, type))

@router.post('/import')
def bulk_import(payload: list[dict], principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok([normalized_repo.create_party(db, principal['tenant_id'], row) for row in payload], 'Bulk import completed')

@router.get('/export')
def export(principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.list_parties(db, principal['tenant_id']))

@router.post('/gstin-lookup')
def gstin_lookup(payload: dict):
    return ok({'gstin':payload.get('gstin'),'status':'mock-verified','legal_name':'GSTIN lookup adapter pending GSP credentials'})

@router.get('/{row_id}')
def get(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(model_dict(normalized_repo.get_party(db, principal['tenant_id'], row_id)))

@router.put('/{row_id}')
def update(row_id: str, payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.update_party(db, principal['tenant_id'], row_id, payload), 'Party updated')

@router.delete('/{row_id}')
def delete(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec=normalized_repo.get_party(db, principal['tenant_id'], row_id); rec.is_deleted=True; return ok(message='Party soft deleted')

@router.get('/{row_id}/ledger')
def ledger(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(normalized_repo.gl_entries(db, principal['tenant_id'], row_id))

@router.get('/{row_id}/outstanding')
def outstanding(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    return ok({'receivable':0,'payable':0})
