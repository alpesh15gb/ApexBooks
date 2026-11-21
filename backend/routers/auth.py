import jwt
import re
from accounting import current_user, db
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from models import AuthSession, SECRET, User, _DUMMY_PASSWORD_HASH, passwords, security
from schemas import Credentials, PasswordChange
from sqlalchemy import select, update
from sqlalchemy.orm import Session


router = APIRouter()


@router.post('/api/auth/register')
def register(body: Credentials, request: Request, session: Session = Depends(db)):
    import book_services as services
    services.auth_throttle(session,request,body.email,"register")
    email = body.email.strip().lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email): raise HTTPException(422, 'Enter a valid email')
    if session.scalar(select(User).where(User.email == email)): raise HTTPException(409, 'Email already registered')
    session.add(User(email=email, password_hash=passwords.hash(body.password))); session.commit()
    return {'message': 'Account created'}


@router.post('/api/auth/login')
def login(body: Credentials, request: Request, session: Session = Depends(db)):
    import book_services as services
    services.auth_throttle(session,request,body.email,"login")
    user = session.scalar(select(User).where(User.email == body.email.strip().lower()).with_for_update().execution_options(populate_existing=True))
    verified_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
    valid=passwords.verify(body.password,verified_hash)
    if not user or not valid:raise HTTPException(401,'Invalid email or password')
    # PostgreSQL serializes this with password reset/change via the User lock.
    # The conditional write also protects SQLite, where FOR UPDATE is ignored:
    # never issue a session after a verified hash has concurrently been replaced.
    unchanged = session.execute(update(User).where(User.id==user.id, User.password_hash==verified_hash)
        .values(password_hash=User.password_hash).execution_options(synchronize_session=False))
    if unchanged.rowcount != 1:raise HTTPException(401,'Password changed; sign in again')
    expires_at = datetime.now(timezone.utc) + timedelta(hours=12)
    auth_session = AuthSession(user_id=user.id, expires_at=expires_at)
    session.add(auth_session); session.flush()
    token = jwt.encode({'sub': user.id, 'jti': auth_session.id, 'exp': expires_at}, SECRET, algorithm='HS256')
    session.commit()
    return {'token': token}


@router.post('/api/auth/logout')
def logout(credentials: HTTPAuthorizationCredentials = Depends(security), user: User = Depends(current_user), session: Session = Depends(db)):
    payload = jwt.decode(credentials.credentials, SECRET, algorithms=['HS256'])
    active = session.get(AuthSession, payload['jti'])
    active.revoked_at = datetime.now(timezone.utc)
    session.commit()
    return {'message': 'Signed out'}


@router.post('/api/auth/logout-other-sessions')
def logout_other_sessions(credentials: HTTPAuthorizationCredentials = Depends(security), user: User = Depends(current_user), session: Session = Depends(db)):
    user=session.scalar(select(User).where(User.id==user.id).with_for_update().execution_options(populate_existing=True))
    current_id = jwt.decode(credentials.credentials, SECRET, algorithms=['HS256'])['jti']
    now = datetime.now(timezone.utc)
    others = list(session.scalars(select(AuthSession).where(AuthSession.user_id == user.id,
        AuthSession.id != current_id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)))
    for active in others: active.revoked_at = now
    session.commit()
    return {'revoked': len(others)}


@router.post('/api/auth/change-password')
def change_password(body: PasswordChange, user: User = Depends(current_user), session: Session = Depends(db)):
    import book_services as services
    user=session.scalar(select(User).where(User.id==user.id).with_for_update().execution_options(populate_existing=True))
    if not passwords.verify(body.current_password, user.password_hash): raise HTTPException(401, 'Current password is incorrect')
    if body.new_password == body.current_password: raise HTTPException(422, 'Choose a different password')
    user.password_hash = passwords.hash(body.new_password)
    services.invalidate_recovery_codes(user.id,session)
    for active in session.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))):
        active.revoked_at = datetime.now(timezone.utc)
    session.commit()
    return {'message': 'Password changed; sign in again'}
