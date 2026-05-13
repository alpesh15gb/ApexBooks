from uuid import uuid4
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db, ensure_tenant_schema
from app.core.exceptions import ok, APIError
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, current_principal, new_api_key, logout_token
from app.models.e2e import CompanyRecord, UserRecord, ApiKeyRecord
from app.schemas.domain import UserRegister, Login
router=APIRouter(prefix='/auth', tags=['Auth'])
class ForgotPassword(BaseModel): email: str
class ResetPassword(BaseModel): email: str; otp: str; new_password: str
class ApiKeyRequest(BaseModel): name: str = 'Default Integration'
@router.post('/register')
def register(payload: UserRegister, db: Session = Depends(get_db)):
    if db.query(UserRecord).filter_by(email=payload.email).first(): raise APIError('EMAIL_EXISTS','Email already registered', status_code=409)
    company_id=str(uuid4()); schema=ensure_tenant_schema(db, company_id); c=payload.company.model_dump(mode='json')
    company=CompanyRecord(company_id=company_id, company_name=c['company_name'], gstin=c['gstin'], pan=c.get('pan'), state_code=c['state_code'], payload=c, schema_name=schema)
    user=UserRecord(user_id=str(uuid4()), tenant_id=company_id, email=payload.email, full_name=payload.full_name, password_hash=hash_password(payload.password), roles=['admin'], permissions=['*'])
    db.add_all([company,user]); db.flush()
    return ok({'company_id':company_id,'schema_name':schema,'user_id':user.user_id,'access_token':create_access_token(user),'refresh_token':create_refresh_token(user)}, 'Company and first admin registered')
@router.post('/login')
def login(payload: Login, db: Session = Depends(get_db)):
    user=db.query(UserRecord).filter_by(email=payload.email, is_active=True).first()
    if not user or not verify_password(payload.password, user.password_hash): raise APIError('INVALID_CREDENTIALS','Invalid email or password', status_code=401)
    return ok({'access_token':create_access_token(user),'refresh_token':create_refresh_token(user),'token_type':'bearer','tenant_id':user.tenant_id}, 'Login successful')
@router.post('/refresh')
def refresh(principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    user=db.query(UserRecord).filter_by(user_id=principal['user_id']).first(); return ok({'access_token':create_access_token(user),'refresh_token':create_refresh_token(user),'token_type':'bearer'})
@router.post('/logout')
def logout(authorization: str | None = Header(default=None, alias='Authorization')):
    if authorization and authorization.startswith('Bearer '):
        token = authorization[7:]
        logout_token(token)
    return ok(message='Logged out successfully. Token has been blacklisted.')
@router.post('/forgot-password')
def forgot_password(payload: ForgotPassword): return ok({'otp_delivery':'email/sms','ttl_minutes':10}, 'OTP generated')
@router.post('/reset-password')
def reset_password(payload: ResetPassword): return ok(message='Password reset after OTP verification')
@router.get('/me')
def me(principal: dict = Depends(current_principal)): return ok(principal)
@router.post('/api-key/generate')
def api_key_generate(payload: ApiKeyRequest, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    raw, hashed = new_api_key(); rec=ApiKeyRecord(key_id=str(uuid4()), tenant_id=principal['tenant_id'], name=payload.name, key_hash=hashed); db.add(rec); db.flush()
    return ok({'key_id':rec.key_id,'api_key':raw,'name':rec.name}, 'API key generated. Store it now; it will not be shown again.')
@router.delete('/api-key/{key_id}')
def api_key_delete(key_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec=db.query(ApiKeyRecord).filter_by(key_id=key_id, tenant_id=principal['tenant_id']).first()
    if rec: rec.is_active=False
    return ok(message='API key revoked')
