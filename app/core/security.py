from datetime import datetime, timedelta
from uuid import uuid4
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import APIError
from app.core.rate_limit import is_token_blacklisted
from app.models.e2e import UserRecord, ApiKeyRecord

pwd_context = CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')
bearer = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str: return pwd_context.hash(password)
def verify_password(password: str, hashed: str) -> bool: return pwd_context.verify(password, hashed)
def hash_api_key(key: str) -> str: return pwd_context.hash(key)
def verify_api_key(key: str, hashed: str) -> bool: return pwd_context.verify(key, hashed)

def create_access_token(user: UserRecord) -> str:
    s = get_settings()
    exp = datetime.utcnow() + timedelta(minutes=s.access_token_expire_minutes)
    jti = uuid4().hex
    payload = {
        'sub': user.user_id,
        'tenant_id': user.tenant_id,
        'roles': user.roles,
        'permissions': user.permissions,
        'exp': exp,
        'jti': jti
    }
    private_key = s.get_jwt_private_key()
    return jwt.encode(payload, private_key, algorithm=s.jwt_algorithm)

def create_refresh_token(user: UserRecord) -> str:
    s = get_settings()
    exp = datetime.utcnow() + timedelta(days=s.refresh_token_expire_days)
    jti = uuid4().hex
    payload = {'sub': user.user_id, 'tenant_id': user.tenant_id, 'typ': 'refresh', 'exp': exp, 'jti': jti}
    private_key = s.get_jwt_private_key()
    return jwt.encode(payload, private_key, algorithm=s.jwt_algorithm)

def decode_token(token: str) -> dict:
    s = get_settings()
    try:
        public_key = s.get_jwt_public_key()
        payload = jwt.decode(token, public_key, algorithms=[s.jwt_algorithm])
        if is_token_blacklisted(payload.get('jti', '')):
            raise APIError('TOKEN_REVOKED', 'Token has been revoked', status_code=401)
        return payload
    except APIError:
        raise
    except JWTError as exc:
        raise APIError('INVALID_TOKEN', 'Token is invalid or expired', status_code=401) from exc

def logout_token(token: str) -> bool:
    try:
        payload = decode_token(token)
        jti = payload.get('jti')
        if jti:
            from app.core.rate_limit import blacklist_token
            exp = payload.get('exp', 0)
            ttl = max(0, int(exp - datetime.utcnow().timestamp()))
            blacklist_token(jti, ttl if ttl > 0 else 86400)
            return True
    except Exception:
        pass
    return False

def current_principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), x_api_key: str | None = Header(default=None, alias='X-API-Key'), db: Session = Depends(get_db)) -> dict:
    if credentials:
        payload = decode_token(credentials.credentials)
        return {'user_id': payload['sub'], 'tenant_id': payload['tenant_id'], 'roles': payload.get('roles', []), 'permissions': payload.get('permissions', [])}
    if x_api_key:
        for rec in db.query(ApiKeyRecord).filter(ApiKeyRecord.is_active == True).all():
            if verify_api_key(x_api_key, rec.key_hash):
                return {'user_id': 'api-key:'+rec.key_id, 'tenant_id': rec.tenant_id, 'roles': ['integration'], 'permissions': ['*']}
    raise APIError('UNAUTHENTICATED', 'Bearer token or X-API-Key required', status_code=401)

def require_permission(permission: str):
    def checker(principal: dict = Depends(current_principal)) -> dict:
        perms = principal.get('permissions', [])
        if '*' not in perms and permission not in perms:
            raise APIError('FORBIDDEN', f'Missing permission: {permission}', status_code=403)
        return principal
    return checker

def new_api_key() -> tuple[str, str]:
    raw = 'gst_' + uuid4().hex + uuid4().hex
    return raw, hash_api_key(raw)
