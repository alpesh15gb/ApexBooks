"""Persistent sign-in throttling and one-use account recovery codes."""
import hashlib,hmac,secrets
from datetime import datetime,timedelta,timezone
from fastapi import Depends,HTTPException,Request
from pydantic import BaseModel,Field
from sqlalchemy import DateTime,ForeignKey,Integer,String,case,delete,select,update
from sqlalchemy.orm import Mapped,Session,mapped_column

class CodeRequest(BaseModel):
    current_password:str=Field(max_length=128)
class RecoverRequest(BaseModel):
    email:str=Field(min_length=3,max_length=254)
    code:str=Field(min_length=1,max_length=128)
    new_password:str=Field(min_length=8,max_length=128)

def install(app,m):
    class RecoveryCode(m.Base):
        __tablename__='auth_recovery_codes'
        digest:Mapped[str]=mapped_column(String(64),primary_key=True)
        user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False,index=True)
        used_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    class RateBucket(m.Base):
        __tablename__='auth_rate_buckets'
        key:Mapped[str]=mapped_column(String(64),primary_key=True)
        started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,index=True)
        attempts:Mapped[int]=mapped_column(Integer,nullable=False)
    def digest(value):return hmac.new(m.SECRET.encode(),value.encode(),hashlib.sha256).hexdigest()
    def consume(session,value,limit,seconds):
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        now=datetime.now(timezone.utc);cutoff=now-timedelta(seconds=seconds)
        statement=(pg_insert if session.bind.dialect.name=='postgresql' else sqlite_insert)(RateBucket).values(key=digest(value),started_at=now,attempts=1)
        statement=statement.on_conflict_do_update(index_elements=['key'],set_={'attempts':case((RateBucket.started_at<=cutoff,1),else_=RateBucket.attempts+1),'started_at':case((RateBucket.started_at<=cutoff,now),else_=RateBucket.started_at)}).returning(RateBucket.attempts,RateBucket.started_at)
        attempts,started=session.execute(statement).one()
        session.execute(delete(RateBucket).where(RateBucket.started_at<now-timedelta(days=1)));session.commit()
        if attempts>limit:
            if started.tzinfo is None:started=started.replace(tzinfo=timezone.utc)
            retry=max(1,int((started+timedelta(seconds=seconds)-now).total_seconds()))
            raise HTTPException(429,'Too many attempts. Try again later.',headers={'Retry-After':str(retry)})
    def throttle(session,request,email,operation):
        # Peer IP is deliberately used unless a trusted platform has already applied
        # proxy-header handling. A caller-supplied forwarded header is never trusted here.
        peer=request.client.host if request.client else 'unknown'
        consume(session,operation+':ip:'+peer,120,60)
        consume(session,operation+':email:'+email.strip().lower(),12,900)
    m.auth_throttle=throttle
    def invalidate(user_id,session):session.execute(update(RecoveryCode).where(RecoveryCode.user_id==user_id).values(used_at=datetime.now(timezone.utc)))
    m.invalidate_recovery_codes=invalidate

    @app.post('/api/auth/recovery-codes')
    def generate(body:CodeRequest,request:Request,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        throttle(session,request,user.email,'generate-recovery')
        user=session.scalar(select(m.User).where(m.User.id==user.id).with_for_update().execution_options(populate_existing=True))
        if not m.passwords.verify(body.current_password,user.password_hash):raise HTTPException(401,'Current password is incorrect')
        codes=['-'.join(secrets.token_hex(5).upper() for _ in range(3)) for _ in range(10)]
        session.execute(delete(RecoveryCode).where(RecoveryCode.user_id==user.id))
        session.add_all([RecoveryCode(digest=digest(user.id+':'+code.replace('-','').lower()),user_id=user.id) for code in codes]);session.commit()
        return {'codes':codes,'message':'Save these codes securely. Each works once. Generating another set invalidates this set.'}

    @app.get('/api/auth/recovery-codes/status')
    def status(user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        rows=list(session.scalars(select(RecoveryCode).where(RecoveryCode.user_id==user.id,RecoveryCode.used_at.is_(None))))
        return {'remaining':len(rows)}

    @app.post('/api/auth/recover')
    def recover(body:RecoverRequest,request:Request,session:Session=Depends(m.db)):
        throttle(session,request,body.email,'recover')
        user=session.scalar(select(m.User).where(m.User.email==body.email.strip().lower()).with_for_update())
        normalized=body.code.replace('-','').replace(' ','').strip().lower()
        code=session.get(RecoveryCode,digest((user.id if user else 'unknown')+':'+normalized))
        if not user or not code or code.user_id!=user.id or code.used_at is not None:raise HTTPException(401,'Invalid email or recovery code')
        user.password_hash=m.passwords.hash(body.new_password);now=datetime.now(timezone.utc)
        # A reset revokes all old sessions and all remaining recovery codes.
        for old in session.scalars(select(RecoveryCode).where(RecoveryCode.user_id==user.id,RecoveryCode.used_at.is_(None))):old.used_at=now
        for active in session.scalars(select(m.AuthSession).where(m.AuthSession.user_id==user.id,m.AuthSession.revoked_at.is_(None))):active.revoked_at=now
        session.commit();return {'message':'Password reset. Sign in and generate a fresh set of recovery codes.'}
