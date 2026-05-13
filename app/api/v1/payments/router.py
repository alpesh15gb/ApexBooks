from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.exceptions import ok
from app.core.security import current_principal
from app.services.normalized_repository import normalized_repo, model_dict
from app.models.accounting import PaymentModel
router=APIRouter(prefix='/payments', tags=['Payments'])
@router.post('/receive')
def receive(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)): payload['payment_type']='Receive'; payload.setdefault('status','Submitted'); return ok(normalized_repo.create_payment(db, principal['tenant_id'], payload))
@router.post('/made')
def made(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)): payload['payment_type']='Pay'; payload.setdefault('status','Submitted'); return ok(normalized_repo.create_payment(db, principal['tenant_id'], payload))
@router.get('')
def list_rows(principal: dict = Depends(current_principal), db: Session = Depends(get_db)): return ok(normalized_repo.list_payments(db, principal['tenant_id']))
@router.get('/{row_id}')
def get(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec=db.query(PaymentModel).filter_by(tenant_id=principal['tenant_id'], payment_id=row_id).first(); return ok(model_dict(rec) if rec else None)
@router.put('/{row_id}')
def update(row_id: str, payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec=db.query(PaymentModel).filter_by(tenant_id=principal['tenant_id'], payment_id=row_id).first()
    if rec:
        for k,v in payload.items():
            if hasattr(rec,k): setattr(rec,k,v)
    return ok(model_dict(rec) if rec else None)
@router.delete('/{row_id}')
def void(row_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec=db.query(PaymentModel).filter_by(tenant_id=principal['tenant_id'], payment_id=row_id).first()
    if rec: rec.status='Voided'
    return ok(model_dict(rec) if rec else None)
@router.post('/{row_id}/reconcile')
def reconcile(row_id: str, payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec=db.query(PaymentModel).filter_by(tenant_id=principal['tenant_id'], payment_id=row_id).first()
    if rec: rec.allocations=payload.get('allocations',[]); rec.status='Reconciled'
    return ok(model_dict(rec) if rec else None)
@router.post('/advance')
def advance(payload: dict, principal: dict = Depends(current_principal), db: Session = Depends(get_db)): payload['is_advance']=True; return ok(normalized_repo.create_payment(db, principal['tenant_id'], payload))
@router.get('/unreconciled')
def unreconciled(principal: dict = Depends(current_principal), db: Session = Depends(get_db)): return ok([p for p in normalized_repo.list_payments(db, principal['tenant_id']) if p.get('status') not in ['Reconciled','Voided']])
@router.post('/auto-reconcile')
def auto_reconcile(principal: dict = Depends(current_principal), db: Session = Depends(get_db)): return ok({'matched':0,'unmatched':len(normalized_repo.list_payments(db, principal['tenant_id']))})
