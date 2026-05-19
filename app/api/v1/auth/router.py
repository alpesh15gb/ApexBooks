import logging
import re
from uuid import uuid4
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db, ensure_tenant_schema
from app.core.exceptions import ok, APIError
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, current_principal, new_api_key, logout_token
from app.models.e2e import CompanyRecord, UserRecord, ApiKeyRecord
from app.schemas.domain import UserRegister, Login
from app.services.email_service import email_service
from app.services.otp_service import otp_service
from app.core.totp import totp_service

logger = logging.getLogger(__name__)


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validate password strength. Returns (is_valid, error_message)."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if len(password) > 128:
        return False, "Password must be less than 128 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    return True, ""

router = APIRouter(prefix='/auth', tags=['Auth'])


class ForgotPassword(BaseModel):
    email: str


class ResetPassword(BaseModel):
    email: str
    otp: str
    new_password: str


class ApiKeyRequest(BaseModel):
    name: str = 'Default Integration'


@router.post('/register')
def register(payload: UserRegister, db: Session = Depends(get_db)):
    if db.query(UserRecord).filter_by(email=payload.email).first():
        raise APIError('EMAIL_EXISTS', 'Email already registered', status_code=409)
    
    # Validate password strength
    valid, err_msg = validate_password_strength(payload.password)
    if not valid:
        raise APIError('WEAK_PASSWORD', err_msg, status_code=400)
    
    company_id = str(uuid4())
    schema = ensure_tenant_schema(db, company_id)
    c = payload.company.model_dump(mode='json')
    
    company = CompanyRecord(
        company_id=company_id,
        company_name=c['company_name'],
        gstin=c['gstin'],
        pan=c.get('pan'),
        state_code=c['state_code'],
        payload=c,
        schema_name=schema
    )
    
    user = UserRecord(
        user_id=str(uuid4()),
        tenant_id=company_id,
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        roles=['admin'],
        permissions=['*']
    )
    
    db.add_all([company, user])
    db.flush()
    
    # Send welcome email
    email_service.send_welcome_email(
        to_email=payload.email,
        full_name=payload.full_name,
        company_name=c['company_name']
    )
    
    return ok({
        'company_id': company_id,
        'schema_name': schema,
        'user_id': user.user_id,
        'access_token': create_access_token(user),
        'refresh_token': create_refresh_token(user)
    }, 'Company and first admin registered')


@router.post('/login')
def login(payload: Login, db: Session = Depends(get_db),
          x_totp_code: str | None = Header(default=None, alias='X-TOTP-Code')):
    user = db.query(UserRecord).filter_by(email=payload.email, is_active=True).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise APIError('INVALID_CREDENTIALS', 'Invalid email or password', status_code=401)

    # Check 2FA
    for p in (user.permissions or []):
        if isinstance(p, str) and p.startswith('totp_enabled:'):
            stored_secret = p[13:]
            if not x_totp_code or not totp_service.verify_otp(stored_secret, x_totp_code):
                raise APIError('TOTP_REQUIRED', 'TOTP code required. Provide X-TOTP-Code header.', status_code=401)
            break

    return ok({
        'access_token': create_access_token(user),
        'refresh_token': create_refresh_token(user),
        'token_type': 'bearer',
        'tenant_id': user.tenant_id
    }, 'Login successful')


@router.post('/refresh')
def refresh(principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    user = db.query(UserRecord).filter_by(user_id=principal['user_id']).first()
    if not user:
        raise APIError('USER_NOT_FOUND', 'User not found', status_code=404)
    return ok({
        'access_token': create_access_token(user),
        'refresh_token': create_refresh_token(user),
        'token_type': 'bearer'
    })


@router.post('/logout')
def logout(authorization: str | None = Header(default=None, alias='Authorization')):
    if authorization and authorization.startswith('Bearer '):
        token = authorization[7:]
        logout_token(token)
    return ok(message='Logged out successfully. Token has been blacklisted.')


@router.post('/forgot-password')
def forgot_password(payload: ForgotPassword, db: Session = Depends(get_db)):
    """Request password reset OTP with rate limiting."""
    email = payload.email.strip().lower()
    
    # Check rate limit
    if not otp_service.check_rate_limit(email, purpose='password_reset'):
        raise APIError('RATE_LIMIT_EXCEEDED', 
            'Too many OTP requests. Please try again after 5 minutes.', 
            status_code=429)
    
    # Check if user exists
    user = db.query(UserRecord).filter_by(email=email, is_active=True).first()
    if not user:
        # Don't reveal if email exists or not (security best practice)
        return ok({'otp_delivery': 'email', 'ttl_minutes': 10}, 'If the email exists, OTP has been sent')
    
    # Increment rate limit counter
    otp_service.increment_rate_limit(email, purpose='password_reset')
    
    # Generate OTP
    otp = otp_service.generate_otp()
    
    # Store OTP with 10 minute expiry
    otp_service.store_otp(email, otp, purpose='password_reset', ttl_seconds=600)
    
    # Send email
    email_sent = email_service.send_password_reset_email(
        to_email=email,
        otp=otp,
        expiry_minutes=10
    )
    
    if not email_sent:
        logger.warning(f"Failed to send email to {email}, but OTP stored for dev mode")
    
    return ok({
        'otp_delivery': 'email',
        'ttl_minutes': 10,
    }, 'If the account exists, an OTP has been sent to your email address')


@router.post('/reset-password')
def reset_password(payload: ResetPassword, db: Session = Depends(get_db)):
    """Reset password with OTP verification and password strength check."""
    email = payload.email.strip().lower()
    
    # Validate password strength
    valid, err_msg = validate_password_strength(payload.new_password)
    if not valid:
        raise APIError('WEAK_PASSWORD', err_msg, status_code=400)
    
    # Verify OTP
    if not otp_service.verify_otp(email, payload.otp, purpose='password_reset'):
        raise APIError('INVALID_OTP', 'Invalid or expired OTP', status_code=400)
    
    # Find user
    user = db.query(UserRecord).filter_by(email=email, is_active=True).first()
    if not user:
        raise APIError('USER_NOT_FOUND', 'User not found', status_code=404)
    
    # Update password
    user.password_hash = hash_password(payload.new_password)
    db.flush()
    
    # Delete OTP and reset rate limit after successful use
    otp_service.delete_otp(email, purpose='password_reset')
    otp_service.reset_rate_limit(email, purpose='password_reset')
    
    return ok(message='Password reset successfully. You can now login with your new password.')


@router.get('/me')
def me(principal: dict = Depends(current_principal)):
    return ok(principal)


@router.post('/api-key/generate')
def api_key_generate(payload: ApiKeyRequest, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    raw, hashed = new_api_key()
    rec = ApiKeyRecord(
        key_id=str(uuid4()),
        tenant_id=principal['tenant_id'],
        name=payload.name,
        key_hash=hashed
    )
    db.add(rec)
    db.flush()
    return ok({
        'key_id': rec.key_id,
        'api_key': raw,
        'name': rec.name
    }, 'API key generated. Store it now; it will not be shown again.')


@router.delete('/api-key/{key_id}')
def api_key_delete(key_id: str, principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    rec = db.query(ApiKeyRecord).filter_by(key_id=key_id, tenant_id=principal['tenant_id']).first()
    if rec:
        rec.is_active = False
    return ok(message='API key revoked')


@router.post('/2fa/enable')
def enable_2fa(principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Enable 2FA for the current user. Returns provisioning URI for QR code."""
    user = db.query(UserRecord).filter_by(user_id=principal['user_id']).first()
    if not user:
        raise APIError('USER_NOT_FOUND', 'User not found', status_code=404)

    secret = totp_service.generate_secret()
    uri = totp_service.get_provisioning_uri(secret, user.email)

    # Store TOTP secret temporarily in user permissions for verification
    current_perms = list(user.permissions or [])
    # Clean old totp entries
    current_perms = [p for p in current_perms if not isinstance(p, str) or not p.startswith('totp:')]
    current_perms.append(f'totp:{secret}')
    user.permissions = current_perms
    db.flush()

    return ok({
        'secret': secret,
        'provisioning_uri': uri,
        'qr_code_url': uri,
    }, '2FA setup initialized. Verify with /auth/2fa/verify to activate.')


@router.post('/2fa/verify')
def verify_2fa(code: str | None = Header(default=None, alias='X-TOTP-Code'),
               principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Verify and activate 2FA by providing current TOTP code."""
    user = db.query(UserRecord).filter_by(user_id=principal['user_id']).first()
    if not user:
        raise APIError('USER_NOT_FOUND', 'User not found', status_code=404)

    if not code:
        raise APIError('MISSING_CODE', 'X-TOTP-Code header is required', status_code=400)

    # Extract stored secret
    stored_secret = None
    for p in (user.permissions or []):
        if isinstance(p, str) and p.startswith('totp:'):
            stored_secret = p[5:]
            break

    if not stored_secret:
        raise APIError('2FA_NOT_SETUP', '2FA not initialized. Call /auth/2fa/enable first.', status_code=400)

    if not totp_service.verify_otp(stored_secret, code):
        raise APIError('INVALID_TOTP', 'Invalid or expired TOTP code.', status_code=401)

    # Mark 2FA as enabled by updating permissions
    new_perms = [p for p in (user.permissions or []) if not (isinstance(p, str) and p.startswith('totp:'))]
    new_perms.append(f'totp_enabled:{stored_secret}')
    user.permissions = new_perms
    db.flush()

    return ok(message='2FA enabled successfully. You will need a TOTP code on next login.')


@router.post('/2fa/disable')
def disable_2fa(principal: dict = Depends(current_principal), db: Session = Depends(get_db)):
    """Disable 2FA for the current user."""
    user = db.query(UserRecord).filter_by(user_id=principal['user_id']).first()
    if not user:
        raise APIError('USER_NOT_FOUND', 'User not found', status_code=404)

    new_perms = [p for p in (user.permissions or []) if not (isinstance(p, str) and (p.startswith('totp:') or p.startswith('totp_enabled:')))]
    user.permissions = new_perms
    db.flush()

    return ok(message='2FA disabled successfully.')
