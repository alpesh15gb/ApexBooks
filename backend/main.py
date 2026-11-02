from advance_tax import prepare as prepare_advance_tax, release as release_advance_tax
import io
import hashlib
import base64
import binascii
import json
import os
import re
import sys
from workflow_extensions import available_credit
from vyapar_import import inspect_backup, master_candidates
from vyapar_audit import transaction_audit
from vyapar_migration import migrate as migrate_vyapar
from urllib.parse import urlparse
from datetime import date as DateType, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from uuid import uuid4

import jwt
import httpx
from fastapi import Depends, FastAPI, HTTPException, Response, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pydantic import BaseModel, Field, ValidationError
from pwdlib import PasswordHash
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Table, LongTable, TableStyle, Paragraph, Spacer
from reportlab.pdfgen import canvas
from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Numeric, String, UniqueConstraint, create_engine, event, select, update, func, or_, case, cast, Text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./apex.db')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+psycopg://', 1)
elif DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)
SECRET = os.getenv('JWT_SECRET', 'development-only-change-me')
if DATABASE_URL.startswith('postgresql') and (SECRET == 'development-only-change-me' or len(SECRET) < 32):
    raise RuntimeError('A unique JWT_SECRET of at least 32 characters is required for PostgreSQL deployments')
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {})
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def enable_sqlite_foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
passwords = PasswordHash.recommended()
_DUMMY_PASSWORD_HASH=passwords.hash('Internal-unusable-comparison-password')
security = HTTPBearer()

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
class Company(Base):
    __tablename__ = 'companies'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String)
    gstin: Mapped[str] = mapped_column(String, default='')
    state_code: Mapped[str] = mapped_column(String, default='')
    address: Mapped[str] = mapped_column(String, default='')
class CompanyTaxProfile(Base):
    __tablename__ = 'company_tax_profiles'
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), primary_key=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)
class CompanyPreference(Base):
    __tablename__ = 'company_preferences'
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), primary_key=True)
    document_template: Mapped[str] = mapped_column(String(16), nullable=False, default='classic')
class CompanyMember(Base):
    __tablename__ = 'company_members'
    __table_args__ = (UniqueConstraint('company_id', 'user_id'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
class Record(Base):
    __tablename__ = 'records'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), index=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, default='')
    number: Mapped[str] = mapped_column(String, default='')
    date: Mapped[DateType] = mapped_column(Date, default=DateType.today)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)

class LedgerAccount(Base):
    __tablename__ = 'ledger_accounts'
    __table_args__ = (UniqueConstraint('company_id', 'code'), UniqueConstraint('company_id', 'id'))
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)

class BankAccount(Base):
    __tablename__ = 'bank_accounts'
    __table_args__ = (UniqueConstraint('company_id', 'name'), UniqueConstraint('company_id', 'ledger_account_id'))
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    ledger_account_id: Mapped[str] = mapped_column(ForeignKey('ledger_accounts.id'), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_hint: Mapped[str] = mapped_column(String(32), nullable=False, default='')

class Journal(Base):
    __tablename__ = 'journals'
    __table_args__ = (UniqueConstraint('company_id', 'id'), UniqueConstraint('company_id', 'reference'))
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    date: Mapped[DateType] = mapped_column(Date, nullable=False)
    reference: Mapped[str] = mapped_column(String(80), nullable=False)
    memo: Mapped[str] = mapped_column(String(500), nullable=False, default='')
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)

class JournalLine(Base):
    __tablename__ = 'journal_lines'
    __table_args__ = (
        ForeignKeyConstraint(['company_id', 'journal_id'], ['journals.company_id', 'journals.id']),
        ForeignKeyConstraint(['company_id', 'account_id'], ['ledger_accounts.company_id', 'ledger_accounts.id']),
        CheckConstraint('(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)', name='one_positive_side'),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    journal_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String, nullable=False)
    debit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    credit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)

class JournalReversal(Base):
    __tablename__ = 'journal_reversals'
    __table_args__ = (
        ForeignKeyConstraint(['company_id', 'original_id'], ['journals.company_id', 'journals.id']),
        ForeignKeyConstraint(['company_id', 'reversal_id'], ['journals.company_id', 'journals.id']),
        UniqueConstraint('company_id', 'original_id'), UniqueConstraint('company_id', 'reversal_id'),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    original_id: Mapped[str] = mapped_column(String, nullable=False)
    reversal_id: Mapped[str] = mapped_column(String, nullable=False)

class PeriodLock(Base):
    __tablename__ = 'period_locks'
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), primary_key=True)
    locked_through: Mapped[DateType] = mapped_column(Date, nullable=False)

class RecordPosting(Base):
    __tablename__ = 'record_postings'
    __table_args__ = (
        ForeignKeyConstraint(['record_id'], ['records.id']),
        ForeignKeyConstraint(['company_id', 'journal_id'], ['journals.company_id', 'journals.id']),
        UniqueConstraint('company_id', 'record_id'), UniqueConstraint('company_id', 'journal_id'),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    record_id: Mapped[str] = mapped_column(String, nullable=False)
    journal_id: Mapped[str] = mapped_column(String, nullable=False)

class DocumentConversion(Base):
    __tablename__ = 'document_conversions'
    __table_args__ = (UniqueConstraint('company_id', 'source_record_id'), UniqueConstraint('company_id', 'target_record_id'))
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    source_record_id: Mapped[str] = mapped_column(ForeignKey('records.id'), nullable=False)
    target_record_id: Mapped[str] = mapped_column(ForeignKey('records.id'), nullable=False)

class IdempotencyKey(Base):
    __tablename__ = 'idempotency_keys'
    __table_args__ = (UniqueConstraint('company_id', 'key'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record_id: Mapped[str] = mapped_column(ForeignKey('records.id'), nullable=False)

class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

class PaymentAllocation(Base):
    __tablename__ = 'payment_allocations'
    __table_args__ = (
        ForeignKeyConstraint(['payment_id'], ['records.id']),
        ForeignKeyConstraint(['document_id'], ['records.id']),
        UniqueConstraint('company_id', 'payment_id'),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    payment_id: Mapped[str] = mapped_column(String, nullable=False)
    document_id: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

class PaymentSplitAllocation(Base):
    __tablename__ = 'payment_split_allocations'
    __table_args__ = (UniqueConstraint('company_id', 'payment_id', 'document_id', name='uq_payment_split_document'),
                      CheckConstraint('amount > 0', name='payment_split_amount_positive'))
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey('records.id'), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('records.id'), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

class BankStatementLine(Base):
    __tablename__ = 'bank_statement_lines'
    __table_args__ = (
        UniqueConstraint('company_id', 'fingerprint'),
        UniqueConstraint('company_id', 'matched_record_id'),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    bank_account_id: Mapped[str | None] = mapped_column(ForeignKey('bank_accounts.id'), nullable=True, index=True)
    date: Mapped[DateType] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    reference: Mapped[str] = mapped_column(String(120), nullable=False, default='')
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    matched_record_id: Mapped[str | None] = mapped_column(ForeignKey('records.id'), nullable=True)

class BankMatchAllocation(Base):
    __tablename__ = 'bank_match_allocations'
    __table_args__ = (UniqueConstraint('company_id', 'statement_line_id', 'record_id'),
                      CheckConstraint('amount > 0', name='bank_match_amount_positive'))
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    statement_line_id: Mapped[str] = mapped_column(ForeignKey('bank_statement_lines.id'), nullable=False, index=True)
    record_id: Mapped[str] = mapped_column(ForeignKey('records.id'), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

class BankReconciliationReview(Base):
    __tablename__ = 'bank_reconciliation_reviews'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    bank_account_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    as_of: Mapped[DateType] = mapped_column(Date, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    statement_closing_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    ledger_closing_balance: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    difference: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    matched: Mapped[int] = mapped_column(nullable=False)
    unmatched: Mapped[int] = mapped_column(nullable=False)
    note: Mapped[str] = mapped_column(String(500), nullable=False, default='')
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

class StockMovement(Base):
    __tablename__ = 'stock_movements'
    __table_args__ = (UniqueConstraint('company_id', 'source_record_id', 'line_index'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey('records.id'), nullable=False, index=True)
    source_record_id: Mapped[str] = mapped_column(ForeignKey('records.id'), nullable=False)
    line_index: Mapped[int] = mapped_column(nullable=False)
    date: Mapped[DateType] = mapped_column(Date, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)
    cost_value: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)

class NumberSeries(Base):
    __tablename__ = 'number_series'
    __table_args__ = (UniqueConstraint('company_id', 'kind', 'financial_year'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    financial_year: Mapped[int] = mapped_column(nullable=False)
    prefix: Mapped[str] = mapped_column(String(6), nullable=False)
    next_number: Mapped[int] = mapped_column(nullable=False, default=1)

app = FastAPI(title='Apex Books API', version='1.3.0', docs_url='/api/docs', redoc_url='/api/redoc', openapi_url='/api/openapi.json')
app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(','), allow_methods=['*'], allow_headers=['*'])
def db():
    from schema_readiness import schema_ready
    if not schema_ready(engine): raise HTTPException(503, 'The database migration for this release is not ready. Please try again shortly.')
    with Session(engine) as session: yield session
def current_user(credentials: HTTPAuthorizationCredentials = Depends(security), session: Session = Depends(db)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET, algorithms=['HS256'])
        user = session.get(User, payload['sub'])
        active = session.scalar(select(AuthSession.id).where(AuthSession.id == payload['jti'], AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > datetime.now(timezone.utc))) if user else None
        if not active: raise ValueError()
        return user
    except (jwt.InvalidTokenError, KeyError, ValueError): raise HTTPException(401, 'Invalid or expired session')
def company_for(company_id: str, user: User, session: Session):
    company = session.scalar(select(Company).where(Company.id == company_id, or_(Company.owner_id == user.id, Company.id.in_(select(CompanyMember.company_id).where(CompanyMember.user_id == user.id)))))
    if not company: raise HTTPException(404, 'Company not found')
    return company
def member_role(company: Company, user: User, session: Session):
    if company.owner_id == user.id: return 'owner'
    member = session.scalar(select(CompanyMember).where(CompanyMember.company_id == company.id, CompanyMember.user_id == user.id))
    if not member: raise HTTPException(404, 'Company not found')
    return member.role
def require_write(company: Company, user: User, session: Session):
    if member_role(company, user, session) not in {'owner', 'editor'}: raise HTTPException(403, 'This company is read only for your account')
def audit(session, company_id, user, action, entity_type, entity_id, details=None):
    session.add(AuditEvent(company_id=company_id, actor_id=user.id, action=action, entity_type=entity_type, entity_id=entity_id, details=details or {}))
def obj(record):
    return {'id': record.id, 'kind': record.kind, 'name': record.name, 'number': record.number, 'date': record.date.isoformat(), 'amount': str(record.amount), 'data': record.data}
def company_obj(c, session, user=None):
    profile = session.get(CompanyTaxProfile, c.id)
    return {'id': c.id, 'name': c.name, 'gstin': c.gstin, 'state_code': c.state_code, 'address': c.address, 'tax_mode': profile.mode if profile else 'regular', 'role': member_role(c, user, session) if user else 'owner'}
class Credentials(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
class CompanyInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    gstin: str = ''
    state_code: str = ''
    address: str = ''
    tax_mode: str = 'regular'
class CompanyPreferenceInput(BaseModel):
    document_template: str
class CompanyUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    gstin: str = Field(default='', max_length=15)
    state_code: str = Field(default='', max_length=2)
    address: str = Field(default='', max_length=500)
class RecordInput(BaseModel):
    kind: str
    name: str = ''
    number: str = ''
    date: DateType = Field(default_factory=DateType.today)
    amount: Decimal = Field(default=Decimal('0'), max_digits=15, decimal_places=2, allow_inf_nan=False)
    data: dict = Field(default_factory=dict)
class AccountInput(BaseModel):
    code: str = Field(min_length=1, max_length=32, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=1, max_length=120)
    category: str
class BankAccountInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    account_hint: str = Field(default='', max_length=32)
class JournalLineInput(BaseModel):
    account_id: str
    debit: Decimal = Field(default=Decimal('0'), ge=0, max_digits=15, decimal_places=2, allow_inf_nan=False)
    credit: Decimal = Field(default=Decimal('0'), ge=0, max_digits=15, decimal_places=2, allow_inf_nan=False)
class JournalInput(BaseModel):
    date: DateType
    reference: str = Field(min_length=1, max_length=80)
    memo: str = Field(default='', max_length=500)
    lines: list[JournalLineInput] = Field(min_length=2, max_length=100)
class ReversalInput(BaseModel):
    date: DateType
    reference: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=500)
class LockInput(BaseModel):
    locked_through: DateType
class StatementInputLine(BaseModel):
    date: DateType
    description: str = Field(min_length=1, max_length=500)
    reference: str = Field(default='', max_length=120)
    amount: Decimal = Field(max_digits=15, decimal_places=2, allow_inf_nan=False)
class StatementImport(BaseModel):
    dry_run: bool = False
    bank_account_id: str = 'default'
    lines: list[StatementInputLine] = Field(min_length=1, max_length=5000)
class MatchInput(BaseModel):
    record_id: str
class BankMatchAllocationInput(BaseModel):
    record_id: str
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2, allow_inf_nan=False)
class ReconciliationReviewInput(BaseModel):
    bank_account_id: str = 'default'
    as_of: DateType
    opening_balance: Decimal = Field(default=Decimal('0'), max_digits=15, decimal_places=2, allow_inf_nan=False)
    note: str = Field(default='', max_length=500)
class MemberInput(BaseModel):
    email: str
    role: str
class SeriesInput(BaseModel):
    kind: str
    financial_year: int = Field(ge=2000, le=2100)
    prefix: str = Field(min_length=1, max_length=6, pattern=r'^[A-Z0-9-]+$')
class OcrInput(BaseModel):
    image_data_url: str = Field(min_length=50, max_length=7_000_000)
class MasterRow(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    gstin: str = Field(default='', max_length=15)
    address: str = Field(default='', max_length=500)
    phone: str = Field(default='', max_length=32)
    email: str = Field(default='', max_length=254)
    party_type: str = Field(default='both', max_length=16)
    hsn: str = Field(default='', max_length=16)
    unit: str = Field(default='', max_length=24)
    sale_rate: Decimal = Field(default=Decimal('0'), ge=0, max_digits=15, decimal_places=2)
    purchase_rate: Decimal = Field(default=Decimal('0'), ge=0, max_digits=15, decimal_places=2)
    gst_rate: Decimal = Field(default=Decimal('0'), ge=0, le=100, max_digits=5, decimal_places=2)
    image_data_url:str=Field(default='',max_length=90000)
    image_thumbnail:str=Field(default='',max_length=22000)
    barcode: str = Field(default='',max_length=80)
    item_type: str = Field(default='goods',pattern=r'^(goods|services)$')
    tax_treatment: str = Field(default='taxable',pattern=r'^(taxable|nil_rated|exempt|non_gst)$')
    track_stock: bool = False
    low_stock_threshold: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=3, allow_inf_nan=False)
    payment_terms_days: int | None = Field(default=None, ge=0, le=3650, strict=True)

def validate_master_defaults(master, kind):
    if master.low_stock_threshold is not None and (kind != 'item' or not master.track_stock or master.item_type != 'goods'):
        raise HTTPException(422, 'Low-stock thresholds require a stock-tracked goods item')
    if master.payment_terms_days is not None and kind != 'party':
        raise HTTPException(422, 'Payment terms belong to a party')

def validate_item_image(master):
    from PIL import Image as PillowImage
    for value in (master.image_data_url,master.image_thumbnail):
        if not value:continue
        try:
            match=re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)',value)
            if not match:raise ValueError()
            raw=base64.b64decode(match.group(2),validate=True)
            if len(raw)>67500:raise ValueError()
            with PillowImage.open(io.BytesIO(raw)) as image:
                if image.width*image.height>1_000_000:raise ValueError()
                image.verify()
        except Exception:raise HTTPException(422,'Use a valid item image below 67 KB and one megapixel')

class MasterImport(BaseModel):
    kind: str
    dry_run: bool = True
    rows: list[MasterRow] = Field(min_length=1, max_length=500)

class OpeningStockInput(BaseModel):
    item_id: str
    date: DateType
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3, allow_inf_nan=False)
    unit_cost: Decimal = Field(gt=0, max_digits=15, decimal_places=2, allow_inf_nan=False)

class StockAdjustmentInput(BaseModel):
    item_id: str
    date: DateType
    direction: str
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3, allow_inf_nan=False)
    unit_cost: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=2, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=500)

def lock_company(company_id, user, session):
    company = company_for(company_id, user, session)
    session.execute(select(Company.id).where(Company.id == company_id).with_for_update()).scalar_one()
    # Recheck access after waiting for the same lock used by membership changes.
    # A revoked editor must not resume a queued posting with stale authorization.
    require_write(company, user, session)
    return company
def require_open_period(company_id, date, session):
    period_lock = session.get(PeriodLock, company_id)
    if period_lock and date <= period_lock.locked_through:
        raise HTTPException(409, 'Date is in a locked accounting period')

KINDS = {'party', 'item', 'sales_invoice', 'estimate', 'proforma', 'sales_order', 'payment_in', 'credit_note', 'pos', 'purchase_bill', 'payment_out', 'expense', 'purchase_order', 'debit_note', 'bank_account', 'bank_transfer'}
DOCUMENTS = {'sales_invoice', 'estimate', 'proforma', 'sales_order', 'credit_note', 'pos', 'purchase_bill', 'purchase_order', 'debit_note', 'expense'}
POSTED_KINDS = {'sales_invoice', 'pos', 'purchase_bill', 'payment_in', 'payment_out', 'expense', 'credit_note', 'debit_note', 'bank_transfer'}
NUMBERED_KINDS = DOCUMENTS | {'payment_in', 'payment_out', 'expense', 'bank_transfer'}
DEFAULT_PREFIXES = {'sales_invoice': 'INV', 'estimate': 'EST', 'proforma': 'PF', 'sales_order': 'SO', 'payment_in': 'PIN', 'credit_note': 'CN', 'pos': 'POS', 'purchase_bill': 'BILL', 'payment_out': 'POUT', 'expense': 'EXP', 'purchase_order': 'PO', 'debit_note': 'DN', 'bank_transfer': 'TRF'}
APPLICATION_KINDS = {'payment_in': 'sales_invoice', 'credit_note': 'sales_invoice', 'payment_out': 'purchase_bill', 'debit_note': 'purchase_bill'}
SYSTEM_ACCOUNTS = {
    'cash': ('SYS-CASH', 'Cash on hand', 'asset'),
    'bank': ('SYS-BANK', 'Bank clearing', 'asset'),
    'receivable': ('SYS-AR', 'Accounts receivable', 'asset'),
    'payable': ('SYS-AP', 'Accounts payable', 'liability'),
    'customer_credits': ('SYS-CUST-CREDIT', 'Customer credit balances', 'liability'),
    'supplier_credits': ('SYS-SUPP-CREDIT', 'Supplier credit balances', 'asset'),
    'rounding': ('SYS-ROUND', 'Transaction rounding', 'expense'),
    'customer_advances': ('SYS-CUST-ADV', 'Customer advances', 'liability'),
    'supplier_advances': ('SYS-SUPP-ADV', 'Supplier advances', 'asset'),
    'sales': ('SYS-SALES', 'Sales income', 'income'),
    'purchases': ('SYS-PURCHASE', 'Purchases and cost', 'expense'),
    'inventory': ('SYS-INVENTORY', 'Tracked inventory at cost', 'asset'),
    'opening_equity': ('SYS-OPENING', 'Opening balances', 'equity'),
    'inventory_gain': ('SYS-STOCK-GAIN', 'Inventory adjustment gains', 'income'),
    'inventory_loss': ('SYS-STOCK-LOSS', 'Inventory adjustment losses', 'expense'),
    'cogs': ('SYS-COGS', 'Cost of goods sold', 'expense'),
    'expenses': ('SYS-EXPENSE', 'General expenses', 'expense'),
    'output_cgst': ('SYS-OUT-CGST', 'Output CGST', 'liability'),
    'output_sgst': ('SYS-OUT-SGST', 'Output SGST', 'liability'),
    'output_igst': ('SYS-OUT-IGST', 'Output IGST', 'liability'),
    'input_cgst': ('SYS-IN-CGST', 'Input CGST pending review', 'asset'),
    'input_sgst': ('SYS-IN-SGST', 'Input SGST pending review', 'asset'),
    'input_igst': ('SYS-IN-IGST', 'Input IGST pending review', 'asset'),
}
def system_account(company_id, key, session):
    code, name, category = SYSTEM_ACCOUNTS[key]
    account = session.scalar(select(LedgerAccount).where(LedgerAccount.company_id == company_id, LedgerAccount.code == code))
    if account:
        if account.name != name or account.category != category: raise HTTPException(409, f'System account {code} has been changed')
        return account.id
    account = LedgerAccount(company_id=company_id, code=code, name=name, category=category)
    session.add(account); session.flush()
    return account.id
def bank_account_for(company_id, bank_account_id, session):
    if not bank_account_id or bank_account_id == 'default': return None
    if not isinstance(bank_account_id, str): raise HTTPException(422, 'Invalid bank account')
    account = session.scalar(select(BankAccount).where(BankAccount.company_id == company_id, BankAccount.id == bank_account_id))
    if not account: raise HTTPException(422, 'Choose a bank account in this company')
    return account
def posting_account(company_id, key, session):
    if key.startswith('bank:'):
        return bank_account_for(company_id, key[5:], session).ledger_account_id
    return system_account(company_id, key, session)
def payment_key(data):
    if data.get('payment_account', 'cash') == 'cash': return 'cash'
    bank_id = str(data.get('bank_account_id') or 'default')
    return 'bank' if bank_id == 'default' else 'bank:' + bank_id
def financial_year_start(value): return value.year if value.month >= 4 else value.year - 1
def next_document_number(company_id, kind, issued, session):
    start = financial_year_start(issued)
    series = session.scalar(select(NumberSeries).where(NumberSeries.company_id == company_id, NumberSeries.kind == kind, NumberSeries.financial_year == start))
    if not series:
        series = NumberSeries(company_id=company_id, kind=kind, financial_year=start, prefix=DEFAULT_PREFIXES[kind], next_number=1)
        session.add(series); session.flush()
    year_label = f'{str(start)[-2:]}-{str(start + 1)[-2:]}'
    while True:
        if series.next_number > 9999: raise HTTPException(409, 'Document series is full for this year')
        number = f'{series.prefix}/{year_label}/{series.next_number:04d}'
        series.next_number += 1
        if len(number) > 16: raise HTTPException(422, 'Generated document number exceeds 16 characters')
        if not session.scalar(select(Record.id).where(Record.company_id == company_id, Record.kind == kind, Record.number == number)):
            return number
def applied_total(company_id,document_id,session,as_of=None):
    total=Decimal('0')
    for model in (PaymentAllocation,PaymentSplitAllocation):
        query=select(func.coalesce(func.sum(model.amount),0)).where(model.company_id==company_id,model.document_id==document_id)
        if as_of is not None:query=query.join(Record,Record.id==model.payment_id).where(Record.company_id==company_id,Record.date<=as_of)
        total+=Decimal(str(session.scalar(query)))
    return total
def posting_lines(kind, amount, data, tax_mode):
    tax = {key: Decimal(str(data.get(key, '0'))) for key in ('cgst', 'sgst', 'igst')}
    pending_input = {key: Decimal(str(data.get('pending_input_' + key, tax[key]))) for key in tax}
    taxable = Decimal(str(data.get('taxable', '0')))
    stock_cost = sum((Decimal(str(line.get('inventory_cost', '0'))) for line in data.get('lines', [])), Decimal('0'))
    lines = []
    round_off = Decimal(str(data.get('round_off',0)))
    def add(key, debit=Decimal('0'), credit=Decimal('0')):
        if debit > 0 or credit > 0: lines.append((key, debit, credit))
    if kind in {'sales_invoice', 'pos', 'credit_note'}:
        reverse = kind == 'credit_note'
        credit_balance = Decimal(str(data.get('unallocated_credit', 0))) if reverse else Decimal('0')
        add(payment_key(data) if kind == 'pos' else 'receivable', credit=amount-credit_balance if reverse else Decimal('0'), debit=Decimal('0') if reverse else amount)
        add('customer_credits', credit=credit_balance)
        add('sales', debit=taxable if reverse else Decimal('0'), credit=Decimal('0') if reverse else taxable)
        for tax_key in tax:
            add('output_' + tax_key, debit=tax[tax_key] if reverse else Decimal('0'), credit=Decimal('0') if reverse else tax[tax_key])
        add('inventory', debit=stock_cost if reverse else Decimal('0'), credit=Decimal('0') if reverse else stock_cost)
        add('cogs', debit=Decimal('0') if reverse else stock_cost, credit=stock_cost if reverse else Decimal('0'))
        adjustment = round_off * (-1 if reverse else 1)
        add('rounding', debit=max(-adjustment,Decimal(0)), credit=max(adjustment,Decimal(0)))
    elif kind in {'purchase_bill', 'debit_note'}:
        reverse = kind == 'debit_note'
        credit_balance = Decimal(str(data.get('unallocated_credit', 0))) if reverse else Decimal('0')
        add('payable', debit=amount-credit_balance if reverse else Decimal('0'), credit=Decimal('0') if reverse else amount)
        add('supplier_credits', debit=credit_balance)
        purchase_cost = amount if tax_mode != 'regular' else amount - sum(pending_input.values())
        remaining_cost = purchase_cost - stock_cost - round_off
        add('inventory', debit=Decimal('0') if reverse else stock_cost, credit=stock_cost if reverse else Decimal('0'))
        signed_remaining = -remaining_cost if reverse else remaining_cost
        add('purchases', debit=max(signed_remaining, Decimal('0')), credit=max(-signed_remaining, Decimal('0')))
        adjustment = round_off * (-1 if reverse else 1)
        add('rounding', debit=max(adjustment,Decimal(0)), credit=max(-adjustment,Decimal(0)))
        if tax_mode == 'regular':
            for tax_key in tax:
                add('input_' + tax_key, debit=Decimal('0') if reverse else pending_input[tax_key], credit=pending_input[tax_key] if reverse else Decimal('0'))
    elif kind == 'payment_in':
        add(payment_key(data), debit=amount)
        advance_tax={key:Decimal(str(data.get('advance_tax',{}).get(key,0))) for key in tax} if data.get('is_advance') else {key:Decimal('0') for key in tax}
        add('customer_advances' if data.get('is_advance') else 'receivable', credit=amount-sum(advance_tax.values()))
        for key,value in advance_tax.items():add('output_'+key,credit=value)
    elif kind == 'payment_out':
        add('supplier_advances' if data.get('is_advance') else 'payable', debit=amount); add(payment_key(data), credit=amount)
    elif kind == 'expense':
        pending = sum(pending_input.values()) if tax_mode == 'regular' else Decimal(0)
        add('expenses', debit=amount-pending-round_off); add(payment_key(data), credit=amount)
        if tax_mode == 'regular':
            for tax_key in tax: add('input_'+tax_key,debit=pending_input[tax_key])
        add('rounding',debit=max(round_off,Decimal(0)),credit=max(-round_off,Decimal(0)))
    elif kind == 'bank_transfer':
        direction=data.get('direction')
        if direction not in {'cash_to_bank','bank_to_cash','bank_to_bank'}:raise HTTPException(422,'Choose a supported transfer direction')
        source=str(data.get('bank_account_id') or 'default');bank_key='bank' if source=='default' else 'bank:'+source
        if direction=='bank_to_bank':
            destination=str(data.get('to_bank_account_id') or 'default')
            if source==destination:raise HTTPException(422,'Choose different source and destination bank accounts')
            target_key='bank' if destination=='default' else 'bank:'+destination
            add(target_key,debit=amount);add(bank_key,credit=amount)
        else:
            add(bank_key if direction=='cash_to_bank' else 'cash',debit=amount)
            add('cash' if direction=='cash_to_bank' else bank_key,credit=amount)
    if sum((debit for _, debit, _ in lines), Decimal('0')) != sum((credit for _, _, credit in lines), Decimal('0')):
        raise HTTPException(422, 'Transaction does not balance; check tax amounts')
    return lines
def money(value): return Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
def calculate(data, company, tax_mode, kind, session):
    lines = data.get('lines', [])
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100: raise HTTPException(422, 'Add 1 to 100 items')
    state = str(data.get('place_of_supply', ''))
    purchase = kind in {'purchase_bill', 'purchase_order', 'debit_note','expense'}
    tax_applies = tax_mode == 'regular' or purchase
    taxable = tax = pending_input_tax = Decimal('0')
    supply_values = {key: Decimal('0') for key in ('taxable', 'nil_rated', 'exempt', 'non_gst')}
    cleaned = []
    try:
        for line in lines:
            if not isinstance(line, dict): raise ValueError()
            description = str(line.get('description', '')).strip()
            hsn = str(line.get('hsn', '')).strip()
            if not description or len(description) > 200 or len(hsn) > 16: raise ValueError()
            qty, rate, gst = Decimal(str(line['quantity'])), Decimal(str(line['rate'])), Decimal(str(line.get('gst_rate', 0)))
            discount_percent = Decimal(str(line.get('discount_percent', 0)))
            if line.get('mrp') not in (None, ''):
                mrp = Decimal(str(line['mrp']))
                if not mrp.is_finite() or mrp < 0 or mrp > Decimal('9999999999999.99') or mrp.as_tuple().exponent < -2: raise ValueError()
            if len(str(line.get('unit', ''))) > 24: raise ValueError()
            if qty <= 0 or rate < 0 or gst < 0 or gst > 100 or discount_percent < 0 or discount_percent > 100 or discount_percent.as_tuple().exponent < -2: raise ValueError()
            if not all(value.is_finite() for value in (qty, rate, gst, discount_percent)): raise ValueError()
            item_id = line.get('item_id')
            if item_id:
                if not isinstance(item_id, str) or len(item_id) > 80: raise HTTPException(422, 'Invalid item selection')
                item = session.scalar(select(Record).where(Record.id == item_id, Record.company_id == company.id, Record.kind == 'item'))
                if not item or item.name.casefold() != description.casefold(): raise HTTPException(422, 'Choose an item from this company and keep its name')
                if item.data.get('track_stock') and (qty.as_tuple().exponent < -3 or qty > Decimal('999999999999.999')):
                    raise HTTPException(422, 'Tracked stock quantity must have at most three decimal places')
            else:
                named_item = session.scalar(select(Record).where(Record.company_id == company.id,
                    Record.kind == 'item', func.lower(Record.name) == description.lower()))
                if named_item and named_item.data.get('track_stock'):
                    raise HTTPException(422, 'Choose the tracked item from this company to post stock')
            if not tax_applies and gst != 0: raise HTTPException(422, 'Non-GST sales cannot charge GST')
            treatment = line.get('tax_treatment', 'taxable')
            if treatment not in supply_values:
                raise HTTPException(422, 'Choose taxable, nil rated, exempt or non-GST treatment')
            if treatment != 'taxable' and gst != 0:
                raise HTTPException(422, 'Nil rated, exempt and non-GST lines cannot charge GST')
            if tax_mode == 'regular' and not purchase and treatment == 'taxable' and gst == 0:
                raise HTTPException(422, 'Classify zero-rate outward supplies as nil rated, exempt or non-GST')
            itc_treatment = line.get('itc_treatment', 'pending_review') if purchase and tax_mode == 'regular' else 'ineligible'
            if itc_treatment not in {'pending_review', 'ineligible'}:
                raise HTTPException(422, 'Choose whether supplier GST is pending input-credit review or ineligible')
            inclusive=line.get('price_includes_tax',False)
            if not isinstance(inclusive,bool):raise ValueError()
            document_discount=Decimal(str(data.get('document_discount_percent',0)))
            if not document_discount.is_finite() or not 0<=document_discount<=100 or document_discount.as_tuple().exponent < -2:raise ValueError()
            gross = money(qty * rate); discount = money(gross * discount_percent / 100)
            if 'discount_amount' in line:
                fixed_discount = Decimal(str(line['discount_amount']))
                if not fixed_discount.is_finite() or fixed_discount < 0 or fixed_discount > gross or fixed_discount.as_tuple().exponent < -2 or discount_percent:
                    raise ValueError()
                discount = fixed_discount
            document_discount_value=money((gross-discount)*document_discount/100)
            net=gross-discount-document_discount_value
            base=money(net/(1+gst/100)) if inclusive else net
            line_tax=net-base if inclusive else money(base*gst/100)
            taxable += base; tax += line_tax
            supply_values[treatment] += base
            if itc_treatment == 'pending_review': pending_input_tax += line_tax
            # Valuation is derived from stock movements, never accepted from a client.
            line = {key: value for key, value in line.items() if key not in {'inventory_cost', 'legacy_shortage_cost'}}
            cleaned.append({**line, 'description': description, 'hsn': hsn, 'gross': str(gross),
                            'discount_percent': str(discount_percent), 'discount': str(discount),'document_discount':str(document_discount_value),
                            'taxable': str(base), 'tax': str(line_tax), 'itc_treatment': itc_treatment,
                            'tax_treatment': treatment})
    except (ValueError, TypeError, KeyError, ArithmeticError, InvalidOperation): raise HTTPException(422, 'Invalid item details, quantity, rate or GST rate')
    if taxable + tax > Decimal('9999999999999.99'): raise HTTPException(422, 'Document amount exceeds supported range')
    if tax_mode == 'regular' and (not company.state_code or not state): raise HTTPException(422, 'Company state code and place of supply are required for GST')
    if tax_mode == 'composition' and kind in {'sales_invoice', 'estimate', 'proforma', 'sales_order', 'credit_note', 'pos'} and state != company.state_code:
        raise HTTPException(422, 'Composition outward supplies must use the company state')
    if tax_mode == 'regular' and data.get('party_gstin') and kind in {'sales_invoice', 'pos', 'credit_note'} and supply_values['taxable'] > 0 and sum((supply_values[key] for key in ('nil_rated', 'exempt', 'non_gst')), Decimal('0')) > 0:
        raise HTTPException(422, 'Issue separate taxable and non-taxable outward documents in this workflow')
    origin_state = str(data.get('supplier_state') or str(data.get('party_gstin') or '')[:2] or company.state_code) if purchase else company.state_code
    if origin_state and not re.fullmatch(r'\d{2}',origin_state):raise HTTPException(422,'Enter a valid supplier state')
    unclassified_supplier_tax = tax_mode != 'regular' and purchase and tax > 0 and (not origin_state or not state)
    intra = tax_applies and origin_state == state and not unclassified_supplier_tax
    cgst = money(tax / 2) if intra else Decimal('0')
    pending_cgst = money(pending_input_tax / 2) if intra else Decimal('0')
    data = {**data, 'tax_mode': tax_mode, 'lines': cleaned, 'taxable': str(taxable),
            'taxable_supply_value': str(supply_values['taxable']), 'nil_rated_value': str(supply_values['nil_rated']),
            'exempt_value': str(supply_values['exempt']), 'non_gst_value': str(supply_values['non_gst']),
            'document_tax_form': 'bill_of_supply' if tax_mode == 'regular' and supply_values['taxable'] == 0 else 'invoice_cum_bill' if tax_mode == 'regular' and supply_values['taxable'] > 0 and sum(supply_values[k] for k in ('nil_rated','exempt','non_gst')) > 0 else 'tax_invoice',
            'cgst': str(cgst), 'sgst': str(tax - cgst if intra else Decimal('0')), 'igst': str(Decimal('0') if intra or unclassified_supplier_tax else tax), 'supplier_tax': str(tax if unclassified_supplier_tax else Decimal('0')),
            'pending_input_cgst': str(pending_cgst), 'pending_input_sgst': str(pending_input_tax - pending_cgst if intra else Decimal('0')),
            'pending_input_igst': str(pending_input_tax if not intra and not unclassified_supplier_tax else Decimal('0')),
            'input_tax_ineligible': str(tax - pending_input_tax if purchase else Decimal('0'))}
    total=money(taxable+tax)
    if data.get('round_total') not in (None,False,True):raise HTTPException(422,'Invalid rounding option')
    rounded=total.quantize(Decimal('1'),rounding=ROUND_HALF_UP) if data.get('round_total') else total
    if rounded > Decimal('9999999999999.99'): raise HTTPException(422, 'Rounded document amount exceeds supported range')
    data={**data,'round_off':str(rounded-total)}
    return data, money(rounded)

def value_stock_lines(company_id, kind, data, tax_mode, issued, target, session):
    if kind not in {'purchase_bill', 'debit_note', 'sales_invoice', 'pos', 'credit_note'}: return data
    if kind in {'credit_note','debit_note'} and data.get('return_stock') is False:
        return {**data,'lines':[{**line,'inventory_cost':'0'} for line in data.get('lines',[])]}
    states = {}
    previous_notes = {}
    if target and kind in {'credit_note', 'debit_note'}:
        posted_notes = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
        for note in session.scalars(select(Record).where(Record.company_id == company_id, Record.kind.in_([kind, 'stock_return'] if kind == 'credit_note' else [kind]), Record.id.in_(posted_notes))):
            if note.data.get('applied_to') != target.id or note.data.get('return_stock') is False: continue
            for line in note.data.get('lines', []):
                item_id = line.get('item_id')
                if item_id:
                    if 'inventory_cost' not in line:
                        raise HTTPException(409, 'Older stock return has no valuation; migrate it before posting')
                    qty, cost = previous_notes.get(item_id, (Decimal('0'), Decimal('0')))
                    previous_notes[item_id] = (qty + Decimal(str(line['quantity'])),
                                               cost + Decimal(str(line.get('inventory_cost', '0'))))
    valued = []
    returned_here = {}
    for line in data.get('lines', []):
        line = dict(line)
        item_id = line.get('item_id')
        item = session.get(Record, item_id) if item_id else None
        if not item or not item.data.get('track_stock'):
            valued.append(line); continue
        if item_id not in states:
            movements = list(session.scalars(select(StockMovement).where(
                StockMovement.company_id == company_id, StockMovement.item_id == item_id).order_by(StockMovement.date, StockMovement.id)))
            if any(m.cost_value is None for m in movements):
                raise HTTPException(409, f'{item.name} has older unvalued stock movements; migrate them before posting')
            if movements and movements[-1].date > issued:
                raise HTTPException(409, f'Post tracked stock for {item.name} on or after {movements[-1].date}')
            states[item_id] = [sum((m.quantity for m in movements), Decimal('0')),
                               sum((m.cost_value for m in movements), Decimal('0'))]
        held_qty, held_value = states[item_id]
        qty = Decimal(str(line['quantity']))
        if kind in {'credit_note', 'debit_note'}:
            source_lines = [original for original in target.data.get('lines', []) if original.get('item_id') == item_id]
            if not source_lines: raise HTTPException(422, f'{item.name} is not linked to the source document')
            if kind == 'credit_note' and any('inventory_cost' not in original for original in source_lines):
                raise HTTPException(409, f'{item.name} source sale has no valuation; migrate it before returning stock')
            source_qty = sum((Decimal(str(original['quantity'])) for original in source_lines), Decimal('0'))
            prior_qty, prior_cost = previous_notes.get(item_id, (Decimal('0'), Decimal('0')))
            now_qty = returned_here.get(item_id, Decimal('0')) + qty
            if prior_qty + now_qty > source_qty:
                raise HTTPException(422, f'{item.name} return quantity exceeds the source document')
            returned_here[item_id] = now_qty
        if kind == 'purchase_bill':
            cost = money(Decimal(str(line['taxable'])) + (Decimal(str(line['tax'])) if tax_mode != 'regular' or line.get('itc_treatment') == 'ineligible' else Decimal('0')))
            if held_qty < 0:
                # Imported Vyapar shortages carry the verified source value of zero.
                # Recognize the replenishment cost for previously sold units now;
                # only units remaining on hand acquire inventory value.
                if held_value != 0: raise HTTPException(409, 'Negative legacy stock has an inconsistent value; review it before replenishing')
                shortage_cost = money(cost * min(qty, -held_qty) / qty)
                line['legacy_shortage_cost'] = str(shortage_cost)
                cost -= shortage_cost
            held_qty += qty; held_value += cost
        elif kind == 'credit_note':
            source_cost = sum((Decimal(str(original.get('inventory_cost', '0'))) for original in source_lines), Decimal('0'))
            remaining_qty = source_qty - prior_qty - (now_qty - qty)
            cost = source_cost - prior_cost - sum((Decimal(str(other.get('inventory_cost', '0'))) for other in valued if other.get('item_id') == item_id), Decimal('0')) if qty == remaining_qty else money(source_cost * qty / source_qty)
            held_qty += qty; held_value += cost
        else:
            if qty > held_qty: raise HTTPException(422, f'Insufficient stock for {item.name}')
            if hasattr(sys.modules[__name__], 'commerce_assert_available'):
                commerce_assert_available(company_id, item_id, qty, held_qty, session)
            cost = held_value if qty == held_qty else money(held_value * qty / held_qty)
            held_qty -= qty; held_value -= cost
        states[item_id] = [held_qty, held_value]
        line['inventory_cost'] = str(cost)
        valued.append(line)
    return {**data, 'lines': valued}

@app.get('/api/health')
def health(session: Session = Depends(db)):
    session.execute(select(1)).scalar_one()
    return {'status': 'ok', 'version': app.version}

@app.get('/api/ready')
def ready(session: Session = Depends(db)):
    return {'status': 'ready', 'version': app.version}

def ocr_configuration():
    base_url = os.getenv('OCR_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
    target = urlparse(base_url)
    if target.scheme not in {'https', 'http'} or not target.netloc or not base_url.endswith('/v1'):
        raise HTTPException(503, 'OCR endpoint configuration is invalid')
    if target.scheme == 'http' and target.hostname not in {'localhost', '127.0.0.1', '::1'} and os.getenv('OCR_ALLOW_INSECURE_HTTP') != '1':
        raise HTTPException(503, 'OCR endpoint must use HTTPS for invoice images')
    external_provider = base_url != 'https://api.openai.com/v1'
    key = (os.getenv('OMNIROUTE_API_KEY') or os.getenv('OMNIROUTE', '')) if external_provider else os.getenv('OPENAI_API_KEY', '')
    if not key: raise HTTPException(503, 'OCR is not configured on this server')
    return base_url, key, os.getenv('OCR_MODEL', os.getenv('OPENAI_OCR_MODEL', 'gpt-4o-mini'))

@app.get('/api/ocr/status')
def ocr_status(user: User = Depends(current_user)):
    try: ocr_configuration()
    except HTTPException as exc: return {'ready': False, 'message': exc.detail}
    return {'ready': True, 'message': 'OCR draft extraction is configured'}

@app.post('/api/companies/{company_id}/ocr/purchase-draft')
def ocr_purchase_draft(company_id: str, body: OcrInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    require_write(company, user, session)
    base_url, key, model = ocr_configuration()
    match = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)', body.image_data_url)
    if not match: raise HTTPException(422, 'Upload a PNG, JPEG or WebP image')
    try: raw = base64.b64decode(match.group(2), validate=True)
    except binascii.Error: raise HTTPException(422, 'Invalid image encoding')
    if len(raw) > 5_000_000: raise HTTPException(413, 'Image exceeds 5 MB')
    image_type = match.group(1)
    signature_ok = (image_type == 'png' and raw.startswith(b'\x89PNG\r\n\x1a\n')
                    or image_type == 'jpeg' and raw.startswith(b'\xff\xd8\xff')
                    or image_type == 'webp' and raw.startswith(b'RIFF') and raw[8:12] == b'WEBP')
    if not signature_ok: raise HTTPException(422, 'Image content does not match its file type')
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['supplier_name','supplier_gstin','supplier_address','place_of_supply','invoice_number','invoice_date','total','items'], 'properties': {
        'supplier_name': {'type': 'string'},'supplier_gstin':{'type':'string'},'supplier_address':{'type':'string'},'place_of_supply':{'type':'string'}, 'invoice_number': {'type': 'string'}, 'invoice_date': {'type': 'string'}, 'total': {'type': 'string'},
        'items': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'required': ['description', 'quantity', 'rate', 'gst_rate', 'hsn'], 'properties': {key: {'type': 'string'} for key in ('description', 'quantity', 'rate', 'gst_rate', 'hsn')}}}
    }}
    payload = {'model': model, 'store': False,
        'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'Extract this purchase invoice into JSON. Use YYYY-MM-DD for date, a two-digit Indian state code for place_of_supply, the printed GSTIN for supplier_gstin, and decimal strings for money and quantities. Rates must exclude GST; when only a tax-inclusive price is printed, derive the pre-tax rate from the explicit printed GST rate. For gst_rate, return the printed percentage as a number string, for example "18" for "18 percent" or "18%". Leave uncertain fields blank. Do not infer input-credit eligibility, tax treatment or missing data.'}, {'type': 'input_image', 'image_url': body.image_data_url, 'detail': 'high'}]}],
        'text': {'format': {'type': 'json_schema', 'name': 'purchase_invoice_draft', 'strict': True, 'schema': schema}}}
    try:
        response = httpx.post(base_url + '/responses', json=payload, headers={'Authorization': 'Bearer ' + key}, timeout=45)
        response.raise_for_status()
        result = response.json()
        text_blocks = [part.get('text', '') for item in result.get('output', []) if item.get('type') == 'message' for part in item.get('content', []) if part.get('type') == 'output_text']
        if not text_blocks: raise ValueError('No extraction returned')
        draft = json.loads(''.join(text_blocks))
        if not isinstance(draft, dict) or not isinstance(draft.get('items'), list): raise ValueError('Invalid extraction')
    except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(502, 'OCR could not extract a draft; enter the bill manually')
    return {'status': 'review_required', 'draft': draft}
@app.post('/api/auth/register')
def register(body: Credentials, request: Request, session: Session = Depends(db)):
    auth_throttle(session,request,body.email,"register")
    email = body.email.strip().lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email): raise HTTPException(422, 'Enter a valid email')
    if session.scalar(select(User).where(User.email == email)): raise HTTPException(409, 'Email already registered')
    session.add(User(email=email, password_hash=passwords.hash(body.password))); session.commit()
    return {'message': 'Account created'}
@app.post('/api/auth/login')
def login(body: Credentials, request: Request, session: Session = Depends(db)):
    auth_throttle(session,request,body.email,"login")
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
@app.post('/api/auth/logout')
def logout(credentials: HTTPAuthorizationCredentials = Depends(security), user: User = Depends(current_user), session: Session = Depends(db)):
    payload = jwt.decode(credentials.credentials, SECRET, algorithms=['HS256'])
    active = session.get(AuthSession, payload['jti'])
    active.revoked_at = datetime.now(timezone.utc)
    session.commit()
    return {'message': 'Signed out'}
@app.post('/api/auth/logout-other-sessions')
def logout_other_sessions(credentials: HTTPAuthorizationCredentials = Depends(security), user: User = Depends(current_user), session: Session = Depends(db)):
    user=session.scalar(select(User).where(User.id==user.id).with_for_update().execution_options(populate_existing=True))
    current_id = jwt.decode(credentials.credentials, SECRET, algorithms=['HS256'])['jti']
    now = datetime.now(timezone.utc)
    others = list(session.scalars(select(AuthSession).where(AuthSession.user_id == user.id,
        AuthSession.id != current_id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)))
    for active in others: active.revoked_at = now
    session.commit()
    return {'revoked': len(others)}
@app.post('/api/auth/change-password')
def change_password(body: PasswordChange, user: User = Depends(current_user), session: Session = Depends(db)):
    user=session.scalar(select(User).where(User.id==user.id).with_for_update().execution_options(populate_existing=True))
    if not passwords.verify(body.current_password, user.password_hash): raise HTTPException(401, 'Current password is incorrect')
    if body.new_password == body.current_password: raise HTTPException(422, 'Choose a different password')
    user.password_hash = passwords.hash(body.new_password)
    invalidate_recovery_codes(user.id,session)
    for active in session.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))):
        active.revoked_at = datetime.now(timezone.utc)
    session.commit()
    return {'message': 'Password changed; sign in again'}
@app.get('/api/companies')
def companies(user: User = Depends(current_user), session: Session = Depends(db)):
    member_companies = select(CompanyMember.company_id).where(CompanyMember.user_id == user.id)
    return [company_obj(c, session, user) for c in session.scalars(select(Company).where(or_(Company.owner_id == user.id, Company.id.in_(member_companies))).order_by(Company.name))]
@app.post('/api/companies')
def create_company(body: CompanyInput, user: User = Depends(current_user), session: Session = Depends(db)):
    if body.tax_mode not in {'regular', 'composition', 'unregistered'}: raise HTTPException(422, 'Unsupported tax profile')
    if body.gstin and not re.fullmatch(r'\d{2}[A-Z0-9]{13}', body.gstin.upper()): raise HTTPException(422, 'GSTIN must contain 15 characters beginning with a state code')
    if body.tax_mode == 'unregistered' and body.gstin: raise HTTPException(422, 'An unregistered company cannot have a GSTIN')
    if body.tax_mode in {'regular','composition'} and not body.gstin:raise HTTPException(422,'A GST registered company needs its GSTIN')
    if body.state_code and not re.fullmatch(r'\d{2}', body.state_code): raise HTTPException(422, 'State code must contain two digits')
    if body.gstin and body.state_code != body.gstin[:2]: raise HTTPException(422, 'GSTIN and state code must match')
    if body.tax_mode in {'regular', 'composition'} and not body.state_code: raise HTTPException(422, 'State code is required for GST registered companies')
    values = body.model_dump(exclude={'tax_mode'}); values['gstin'] = body.gstin.upper()
    c = Company(owner_id=user.id, **values); session.add(c); session.flush(); session.add(CompanyTaxProfile(company_id=c.id, mode=body.tax_mode)); session.add(CompanyPreference(company_id=c.id,document_template='modern')); audit(session, c.id, user, 'company.created', 'company', c.id, {'tax_mode': body.tax_mode}); session.commit(); session.refresh(c); return company_obj(c, session)

@app.patch('/api/companies/{company_id}')
def update_company(company_id: str, body: CompanyUpdate, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can update company details')
    profile = session.get(CompanyTaxProfile, company_id)
    mode = profile.mode if profile else 'regular'
    gstin = body.gstin.strip().upper()
    state = body.state_code.strip()
    if not body.name.strip(): raise HTTPException(422, 'Company name is required')
    if gstin and not re.fullmatch(r'\d{2}[A-Z0-9]{13}', gstin): raise HTTPException(422, 'GSTIN must contain 15 characters beginning with a state code')
    if state and not re.fullmatch(r'\d{2}', state): raise HTTPException(422, 'State code must contain two digits')
    if gstin and gstin[:2] != state: raise HTTPException(422, 'GSTIN and state code must match')
    if mode in {'regular', 'composition'} and not state: raise HTTPException(422, 'State code is required for GST registered companies')
    if mode == 'composition' and not gstin: raise HTTPException(422, 'A composition company needs its GSTIN')
    if mode == 'unregistered' and gstin: raise HTTPException(422, 'An unregistered company cannot have a GSTIN')
    company.name = body.name.strip(); company.gstin = gstin; company.state_code = state; company.address = body.address.strip()
    audit(session, company_id, user, 'company.updated', 'company', company_id)
    session.commit()
    return company_obj(company, session, user)

@app.get('/api/companies/{company_id}/preferences')
def get_preferences(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    preference = session.get(CompanyPreference, company_id)
    return {'document_template': preference.document_template if preference else 'classic'}

class DocumentBranding(BaseModel):
    phone: str = Field(default='', max_length=32)
    email: str = Field(default='', max_length=254)
    bank_name: str = Field(default='', max_length=120)
    account_number: str = Field(default='', max_length=64)
    ifsc: str = Field(default='', max_length=20)
    branch: str = Field(default='', max_length=120)
    upi_id: str = Field(default='', max_length=120)
    notes: str = Field(default='', max_length=1500)
    terms: str = Field(default='', max_length=3000)
    logo: str = Field(default='', max_length=350000)
    signature: str = Field(default='', max_length=350000)

def branding_for(company_id, session):
    row = session.scalar(select(Record).where(Record.company_id == company_id, Record.kind == 'document_branding'))
    return row.data if row else {}

@app.get('/api/companies/{company_id}/document-branding')
def get_branding(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    return branding_for(company_id, session)

@app.put('/api/companies/{company_id}/document-branding')
def set_branding(company_id: str, body: DocumentBranding, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can change document branding')
    # An omitted asset is not a request to delete it. In particular, saving bank
    # details from another client must not silently clear the company logo.
    existing_branding = branding_for(company_id, session)
    supplied_branding = body.model_dump(exclude_unset=True)
    body = DocumentBranding.model_validate({**existing_branding, **supplied_branding})
    saved_branding = body.model_dump()
    for asset in ('logo', 'signature'):
        if asset not in existing_branding and asset not in supplied_branding:
            saved_branding.pop(asset, None)
    from PIL import Image as PillowImage
    for value in (body.logo, body.signature):
        if not value: continue
        try:
            match = re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)', value)
            if not match: raise ValueError()
            raw = base64.b64decode(match.group(2), validate=True)
            if len(raw) > 250000: raise ValueError()
            with PillowImage.open(io.BytesIO(raw)) as image:
                if image.format not in {'PNG', 'JPEG'} or image.width * image.height > 4_000_000: raise ValueError()
                image.verify()
        except Exception: raise HTTPException(422, 'Logo and signature must be valid PNG/JPEG images under 250 KB and 4 megapixels')
    row = session.scalar(select(Record).where(Record.company_id == company_id, Record.kind == 'document_branding'))
    if row: row.data = saved_branding
    else: session.add(Record(company_id=company_id, kind='document_branding', name='Document branding', date=DateType.today(), amount=Decimal('0'), data=saved_branding))
    audit(session, company_id, user, 'document_branding.updated', 'company', company_id)
    session.commit()
    return saved_branding

@app.patch('/api/companies/{company_id}/document-branding')
def patch_branding(company_id: str, body: DocumentBranding, user: User = Depends(current_user), session: Session = Depends(db)):
    return set_branding(company_id, body, user, session)

@app.put('/api/companies/{company_id}/preferences')
def set_preferences(company_id: str, body: CompanyPreferenceInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can change company preferences')
    if body.document_template not in {'classic', 'modern', 'compact', 'bold', 'minimal', 'elegant', 'vintage', 'mrp_discount', 'evergreen'}:
        raise HTTPException(422, 'Unsupported document layout')
    preference = session.get(CompanyPreference, company_id)
    if preference: preference.document_template = body.document_template
    else: session.add(CompanyPreference(company_id=company_id, document_template=body.document_template))
    audit(session, company_id, user, 'preferences.updated', 'company', company_id, {'document_template': body.document_template})
    session.commit()
    return {'document_template': body.document_template}

@app.get('/api/companies/{company_id}/audit-events')
def audit_events(company_id: str, limit: int = Query(default=50, ge=1, le=200), user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can view the activity log')
    rows = session.scalars(select(AuditEvent).where(AuditEvent.company_id == company_id).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(limit))
    return [{'id': row.id, 'occurred_at': row.occurred_at.isoformat(), 'actor': session.get(User, row.actor_id).email,
             'action': row.action, 'entity_type': row.entity_type, 'entity_id': row.entity_id, 'details': row.details} for row in rows]

@app.get('/api/companies/{company_id}/members')
def list_members(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    rows = [(session.get(User, company.owner_id).email, 'owner')]
    rows += [(session.get(User, m.user_id).email, m.role) for m in session.scalars(select(CompanyMember).where(CompanyMember.company_id == company_id))]
    return [{'email': email, 'role': role} for email, role in rows]

@app.post('/api/companies/{company_id}/members', status_code=201)
def add_member(company_id: str, body: MemberInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can manage members')
    if body.role not in {'editor', 'viewer'}: raise HTTPException(422, 'Role must be editor or viewer')
    invitee = session.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not invitee: raise HTTPException(404, 'User must register before being added')
    if invitee.id == user.id: raise HTTPException(409, 'Owner already has access')
    member = CompanyMember(company_id=company_id, user_id=invitee.id, role=body.role)
    session.add(member)
    audit(session, company_id, user, 'member.added', 'user', invitee.id, {'role': body.role})
    try: session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'User already has access')
    return {'email': invitee.email, 'role': member.role}

@app.delete('/api/companies/{company_id}/members/{member_email}')
def remove_member(company_id: str, member_email: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can manage members')
    invitee = session.scalar(select(User).where(User.email == member_email.strip().lower()))
    member = session.scalar(select(CompanyMember).where(CompanyMember.company_id == company_id, CompanyMember.user_id == invitee.id)) if invitee else None
    if not member: raise HTTPException(404, 'Member not found')
    session.delete(member); audit(session, company_id, user, 'member.removed', 'user', invitee.id); session.commit()
    return {'removed': True}

@app.get('/api/companies/{company_id}/number-series')
def list_number_series(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    rows = session.scalars(select(NumberSeries).where(NumberSeries.company_id == company_id).order_by(NumberSeries.financial_year.desc(), NumberSeries.kind))
    return [{'kind': r.kind, 'financial_year': r.financial_year, 'prefix': r.prefix, 'next_number': r.next_number} for r in rows]

@app.put('/api/companies/{company_id}/number-series')
def set_number_series(company_id: str, body: SeriesInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can change numbering')
    if body.kind not in NUMBERED_KINDS: raise HTTPException(422, 'Unsupported document type')
    row = session.scalar(select(NumberSeries).where(NumberSeries.company_id == company_id, NumberSeries.kind == body.kind, NumberSeries.financial_year == body.financial_year))
    if row: row.prefix = body.prefix
    else:
        row = NumberSeries(company_id=company_id, kind=body.kind, financial_year=body.financial_year, prefix=body.prefix, next_number=1)
        session.add(row)
    audit(session, company_id, user, 'number_series.updated', 'company', company_id, {'kind': body.kind, 'financial_year': body.financial_year, 'prefix': body.prefix})
    session.commit()
    return {'kind': row.kind, 'financial_year': row.financial_year, 'prefix': row.prefix, 'next_number': row.next_number}
def compact_record_data(dialect):
    """Trim heavy snapshots in SQL, before database transfer/JSON deserialization."""
    masters = Record.kind.in_(['item', 'party'])
    if dialect == 'postgresql':
        from sqlalchemy.dialects.postgresql import JSONB, ARRAY
        data = cast(Record.data, JSONB)
        for key in ('vyapar_source', 'image_data_url', 'company_snapshot', 'document_branding'):
            data = data.op('-')(key)
        return case((masters, data), else_=func.jsonb_set(data, cast(['lines'], ARRAY(Text)), cast('[]', JSONB)))
    if dialect == 'sqlite':
        data = func.json_remove(Record.data, '$.vyapar_source', '$.image_data_url',
            '$.company_snapshot', '$.document_branding', type_=JSON)
        return case((masters, data), else_=func.json_set(data, '$.lines', func.json('[]'), type_=JSON))
    return Record.data


@app.get('/api/companies/{company_id}/records')
def records(company_id: str, kind: str = '', compact:bool=False, offset:int=Query(default=0,ge=0),limit:int|None=Query(default=None,ge=1,le=500),user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    projected = compact and session.bind.dialect.name in {'postgresql', 'sqlite'}
    q = select(Record.id, Record.kind, Record.name, Record.number, Record.date, Record.amount,
        compact_record_data(session.bind.dialect.name).label('data')) if projected else select(Record)
    q = q.where(Record.company_id == company_id, Record.kind.not_in(['vyapar_backup_archive','document_branding','restore_marker']))
    if kind:q=q.where(Record.kind==kind)
    created_at = func.coalesce(Record.data['created_at'].as_string(), '')
    q=q.order_by(Record.date.desc(),created_at.desc(),Record.id.desc()).offset(offset)
    if limit:q=q.limit(limit)
    if projected:
        from types import SimpleNamespace
        rows=[SimpleNamespace(**row) for row in session.execute(q).mappings()]
    else:rows=list(session.scalars(q))
    if not rows:return []
    page_ids=[row.id for row in rows]
    posted=set(session.scalars(select(RecordPosting.record_id).where(RecordPosting.company_id==company_id,RecordPosting.record_id.in_(page_ids))))
    draft_ids=[row.id for row in rows if row.kind in DOCUMENTS-POSTED_KINDS]
    conversions=dict(session.execute(select(DocumentConversion.source_record_id,DocumentConversion.target_record_id).where(
        DocumentConversion.company_id==company_id,DocumentConversion.source_record_id.in_(draft_ids))).all()) if draft_ids else {}
    consumed={};credit_used={};applied={}
    document_ids=[row.id for row in rows if row.kind in {'sales_invoice','purchase_bill','opening_receivable','opening_payable'} and row.id in posted]
    if document_ids:
        for model in (PaymentAllocation,PaymentSplitAllocation):
            for did,value in session.execute(select(model.document_id,func.sum(model.amount)).where(
                model.company_id==company_id,model.document_id.in_(document_ids)).group_by(model.document_id)):
                applied[did]=applied.get(did,Decimal('0'))+value
    balance_ids=[row.id for row in rows if row.id in posted and (row.data.get('is_advance') or row.kind in {'credit_note','debit_note'})]
    if balance_ids:
        advance_id=Record.data['advance_id'].as_string();note_id=Record.data['credit_note_id'].as_string()
        posted_ids=select(RecordPosting.record_id).where(RecordPosting.company_id==company_id)
        settlements=session.execute(select(advance_id,note_id,func.sum(Record.amount)).where(
            Record.company_id==company_id,Record.id.in_(posted_ids),
            Record.kind.in_(['advance_application','advance_refund','credit_application','customer_refund','supplier_refund']),
            or_(advance_id.in_(balance_ids),note_id.in_(balance_ids))).group_by(advance_id,note_id))
        for source_id,credit_id,amount in settlements:
            if source_id:consumed[source_id]=consumed.get(source_id,Decimal('0'))+amount
            if credit_id:credit_used[credit_id]=credit_used.get(credit_id,Decimal('0'))+amount
    result=[]
    for row in rows:
        value=obj(row)
        if compact and not projected:
            data={k:v for k,v in row.data.items() if k not in {'vyapar_source','image_data_url','company_snapshot','document_branding'}}
            if row.kind not in {'item','party'}:data['lines']=[]
            if isinstance(data.get('document_branding'),dict):data['document_branding']={k:v for k,v in data['document_branding'].items() if k not in {'logo','signature'}}
            value['data']=data
        result.append({**value, **record_status(row, row.id in posted,
            applied=applied.get(row.id, Decimal('0')), consumed=consumed.get(row.id, Decimal('0')),
            credit_used=credit_used.get(row.id, Decimal('0')), converted_to=conversions.get(row.id))})
    return result

def record_status(row, posted, *, applied=Decimal('0'), consumed=Decimal('0'), credit_used=Decimal('0'), converted_to=None):
    """Identical fresh lifecycle fields for compact lists and full detail clients."""
    return {'posted': posted,
        'advance_remaining': str(row.amount-consumed) if row.data.get('is_advance') and posted else None,
        'credit_remaining': str(Decimal(str(row.data.get('unallocated_credit',0)))-credit_used) if row.kind in {'credit_note','debit_note'} and posted else None,
        'converted_to': converted_to or ('source-converted' if row.data.get('vyapar_converted') else None),
        'outstanding': str(row.amount-applied) if row.kind in {'sales_invoice','purchase_bill','opening_receivable','opening_payable'} and posted else None}

@app.get('/api/companies/{company_id}/records/{record_id}')
def get_record(company_id:str,record_id:str,user:User=Depends(current_user),session:Session=Depends(db)):
    company_for(company_id,user,session)
    row=session.scalar(select(Record).where(Record.company_id==company_id,Record.id==record_id,Record.kind.not_in(['vyapar_backup_archive','restore_marker','document_branding'])))
    if not row:raise HTTPException(404,'Record not found')
    allocations=[]
    for model in (PaymentAllocation,PaymentSplitAllocation):allocations += [{'document_id':r.document_id,'amount':str(r.amount)} for r in session.scalars(select(model).where(model.company_id==company_id,model.payment_id==row.id))]
    posted_ids = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    posted = bool(session.scalar(select(RecordPosting.id).where(RecordPosting.company_id==company_id,RecordPosting.record_id==row.id)))
    settlements = list(session.scalars(select(Record).where(Record.company_id==company_id, Record.id.in_(posted_ids),
        Record.kind.in_(['advance_application','advance_refund','credit_application','customer_refund','supplier_refund']),
        or_(Record.data['advance_id'].as_string()==row.id, Record.data['credit_note_id'].as_string()==row.id))))
    consumed = sum((r.amount for r in settlements if r.data.get('advance_id')==row.id), Decimal('0'))
    credit_used = sum((r.amount for r in settlements if r.data.get('credit_note_id')==row.id), Decimal('0'))
    converted_to = session.scalar(select(DocumentConversion.target_record_id).where(DocumentConversion.company_id==company_id, DocumentConversion.source_record_id==row.id))
    return {**obj(row), **record_status(row, posted, applied=applied_total(company_id,row.id,session),
        consumed=consumed, credit_used=credit_used, converted_to=converted_to), 'allocations':allocations}

@app.post('/api/companies/{company_id}/advances/{advance_id}/apply')
def apply_advance(company_id: str, advance_id: str, body: RecordInput, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    return apply_advance_in_transaction(company_id, advance_id, body, request, user, session)

def apply_advance_in_transaction(company_id, advance_id, body, request, user, session, *, commit=True):
    lock_company(company_id, user, session)
    key = request.headers.get('Idempotency-Key', '').strip()
    if not key or len(key) > 80: raise HTTPException(422, 'A valid idempotency key is required')
    fingerprint = hashlib.sha256(json.dumps({'advance_id': advance_id, 'body': body.model_dump(mode='json')}, sort_keys=True).encode()).hexdigest()
    previous = session.scalar(select(IdempotencyKey).where(IdempotencyKey.company_id == company_id, IdempotencyKey.key == key))
    if previous:
        if previous.request_hash != fingerprint: raise HTTPException(409, 'Idempotency key was used for a different request')
        return {**obj(session.get(Record, previous.record_id)), 'posted': True}
    require_open_period(company_id, body.date, session)
    source = session.scalar(select(Record).where(Record.company_id == company_id, Record.id == advance_id))
    if not source or source.kind not in {'payment_in', 'payment_out'} or not source.data.get('is_advance'):
        raise HTTPException(404, 'Advance not found')
    if not session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id, RecordPosting.record_id == source.id)):
        raise HTTPException(422, 'Advance must be posted')
    target_id = body.data.get('applied_to')
    if not isinstance(target_id, str): raise HTTPException(422, 'Choose an invoice or bill')
    target = session.scalar(select(Record).where(Record.company_id == company_id, Record.id == target_id, Record.kind == APPLICATION_KINDS[source.kind]))
    if not target or not session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id, RecordPosting.record_id == target.id)):
        raise HTTPException(422, 'Choose a posted invoice or bill in this company')
    if source.name.strip().casefold() != target.name.strip().casefold(): raise HTTPException(422, 'Party must match the advance')
    if body.date < max(source.date, target.date): raise HTTPException(422, 'Application date cannot precede the advance or document')
    amount = money(body.amount)
    used = sum((r.amount for r in session.scalars(select(Record).where(Record.company_id == company_id, Record.kind.in_(['advance_application','advance_refund']))) if r.data.get('advance_id') == source.id), Decimal('0'))
    if amount <= 0 or amount > source.amount - used: raise HTTPException(422, 'Amount exceeds the available advance')
    if amount > target.amount - applied_total(company_id, target.id, session): raise HTTPException(422, 'Amount exceeds the outstanding document balance')
    advance_base,advance_taxes,advance_data=release_advance_tax(sys.modules[__name__],company_id,source,amount,used,session,target)
    application = Record(company_id=company_id, kind='advance_application', name=source.name, date=body.date, amount=amount,
        data={**advance_data,'applied_to':target.id})
    session.add(application); session.flush()
    application.number = 'ADV-' + application.id[:8].upper()
    journal = Journal(company_id=company_id, date=body.date, reference='AUTO:' + application.id, memo='Advance application ' + application.number, created_by=user.id)
    session.add(journal); session.flush()
    debit, credit = ('customer_advances', 'receivable') if source.kind == 'payment_in' else ('payable', 'supplier_advances')
    debit_value=advance_base if source.kind=='payment_in' else amount
    if debit_value:session.add(JournalLine(company_id=company_id,journal_id=journal.id,account_id=system_account(company_id,debit,session),debit=debit_value,credit=Decimal('0')))
    session.add_all([
        JournalLine(company_id=company_id, journal_id=journal.id, account_id=system_account(company_id, credit, session), debit=Decimal('0'), credit=amount),
        RecordPosting(company_id=company_id, record_id=application.id, journal_id=journal.id),
        PaymentSplitAllocation(company_id=company_id, payment_id=application.id, document_id=target.id, amount=amount),
        IdempotencyKey(company_id=company_id, key=key, request_hash=fingerprint, record_id=application.id)])
    for tax_key,tax_value in advance_taxes.items():
        if tax_value:session.add(JournalLine(company_id=company_id,journal_id=journal.id,account_id=system_account(company_id,'output_'+tax_key,session),debit=tax_value,credit=Decimal('0')))
    audit(session, company_id, user, 'advance.applied', 'advance_application', application.id, {'advance_id': source.id, 'document_id': target.id, 'amount': str(amount)})
    if commit: session.commit()
    else: session.flush()
    return {**obj(application), 'posted': True}

class VyaparImportInput(BaseModel):
    backup_base64: str = Field(max_length=4_000_000)
    digest: str = ''

@app.post('/api/companies/{company_id}/imports/vyapar-posting/{action}')
def vyapar_full_posting(company_id: str, action: str, body: VyaparImportInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can migrate a backup')
    if action not in {'preview', 'commit'}: raise HTTPException(404, 'Unknown migration action')
    try:
        backup = inspect_backup(body.backup_base64)
        return migrate_vyapar(company, user, session, backup, action, body.digest)
    except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
        session.rollback()
        raise HTTPException(422, 'Unsupported source data; migration was not posted') from exc

@app.get('/api/companies/{company_id}/imports/vyapar-posting/reconciliation')
def vyapar_reconciliation(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can view the migration reconciliation')
    archive = session.scalar(select(Record).where(Record.company_id == company_id, Record.kind == 'vyapar_backup_archive'))
    if not archive or archive.data.get('scope') != 'full_posting': raise HTTPException(404, 'No posted migration found')
    return archive.data['posting_summary']

@app.post('/api/companies/{company_id}/imports/vyapar/{action}')
def vyapar_import(company_id: str, action: str, body: VyaparImportInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can import a backup')
    if action not in {'preview', 'commit'}: raise HTTPException(404, 'Import action not found')
    try: backup = inspect_backup(body.backup_base64)
    except ValueError as exc: raise HTTPException(422, str(exc))
    tables, digest = backup['tables'], backup['digest']
    archives = list(session.scalars(select(Record).where(Record.company_id == company_id, Record.kind == 'vyapar_backup_archive')))
    existing = next((r for r in archives if r.data.get('digest') == digest), None)
    if existing: return {'already_imported': True, 'digest': digest, 'archive_id': existing.id, 'counts': backup['counts'],
        'mapping_audit': transaction_audit(tables), 'archive_missing_tables': [name for name in tables if name not in existing.data.get('tables', {})]}
    if archives: raise HTTPException(409, 'This company already has a different Vyapar backup; use a separate company for another backup')
    if session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id)):
        raise HTTPException(409, 'Use a company without posted accounting entries for backup migration')
    names = {(r.kind, r.name.strip().casefold()) for r in session.scalars(select(Record).where(Record.company_id == company_id, Record.kind.in_(['party', 'item'])))}
    errors, ready, skipped = [], [], []
    for kind, source_id, values, original in master_candidates(tables):
        try:
            values['name'] = values['name'].strip()
            if kind == 'item':
                for key in ('sale_rate', 'purchase_rate', 'gst_rate'): values[key] = str(money(Decimal(str(values[key]))))
            row = MasterRow.model_validate(values)
            if not row.name: raise ValueError('Name is empty')
            if row.gstin and not re.fullmatch(r'\d{2}[A-Z0-9]{13}', row.gstin.upper()): raise ValueError('Invalid GSTIN')
            if row.email and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', row.email): raise ValueError('Invalid email')
            identity = (kind, row.name.casefold())
            if identity in names:
                skipped.append({'kind': kind, 'source_id': source_id, 'name': row.name}); continue
            names.add(identity)
            ready.append((kind, source_id, row, original))
        except (ValidationError, ValueError, InvalidOperation):
            errors.append({'kind': kind, 'source_id': source_id, 'name': str(values.get('name', ''))[:120], 'error': 'Check name length, contact fields, GSTIN and numeric values in the source backup'})
    report = {'digest': digest, 'company_name': str(tables['kb_firms'][0].get('firm_name') or ''), 'counts': backup['counts'],
        'mapping_audit': transaction_audit(tables),
        'ready': {'parties': sum(kind == 'party' for kind, *_ in ready), 'items': sum(kind == 'item' for kind, *_ in ready)},
        'skipped_duplicates': skipped, 'errors': errors,
        'scope': 'masters_and_source_archive', 'warnings': ['Transactions, links, opening balances and stock quantities are retained in a source archive. They do not post journals, stock movements or tax returns.', 'Expense categories remain in the archive; imported parties are marked customer and supplier.', 'Master prices are rounded to two decimals; original values are preserved. Stock tracking is disabled until opening stock is reviewed.', 'Images, attachments, app settings and user accounts are not imported.']}
    if action == 'preview': return report
    if body.digest != digest: raise HTTPException(409, 'Preview this exact backup before importing')
    if errors: raise HTTPException(422, 'Correct the preview errors before importing')
    for kind, source_id, row, original in ready:
        data = row.model_dump(mode='json', exclude={'name'})
        data.update({'vyapar_source_id': source_id, 'vyapar_source': original, 'gstin': row.gstin.upper()})
        session.add(Record(company_id=company_id, kind=kind, name=row.name, amount=Decimal('0'), date=DateType.today(), data=data))
    archive = Record(company_id=company_id, kind='vyapar_backup_archive', name=report['company_name'][:120], date=DateType.today(), amount=Decimal('0'),
        data={'digest': digest, 'archive_version': 2, 'scope': report['scope'], 'tables': tables, 'summary': report})
    session.add(archive); session.flush()
    audit(session, company_id, user, 'vyapar.imported', 'vyapar_backup_archive', archive.id, {'digest': digest, 'counts': report['ready']})
    session.commit()
    return {**report, 'archive_id': archive.id, 'imported': True}

@app.get('/api/companies/{company_id}/imports/vyapar/archive.json')
def vyapar_archive(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can export the source archive')
    archive = session.scalar(select(Record).where(Record.company_id == company_id, Record.kind == 'vyapar_backup_archive'))
    if not archive: raise HTTPException(404, 'No Vyapar archive imported')
    return Response(json.dumps(archive.data, ensure_ascii=False), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="vyapar-source-archive.json"'})

@app.post('/api/companies/{company_id}/masters/import')
def import_masters(company_id: str, body: MasterImport, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    if body.kind not in {'party', 'item'}: raise HTTPException(422, 'Import supports parties and items only')
    existing = {r.name.strip().casefold() for r in session.scalars(select(Record).where(Record.company_id == company_id, Record.kind == body.kind))}
    seen = set()
    errors, ready, duplicates = [], [], 0
    for index, row in enumerate(body.rows, 2):
        name = row.name.strip()
        key = name.casefold()
        if not key:
            errors.append({'row': index, 'message': 'Name is required'}); continue
        if key in existing or key in seen:
            duplicates += 1; continue
        try:validate_master_defaults(row, body.kind)
        except HTTPException as exc:
            errors.append({'row': index, 'message': exc.detail});continue
        data = row.model_dump(mode='json', exclude={'name'})
        if body.kind == 'party':
            if row.party_type not in {'customer', 'supplier', 'both'}:
                errors.append({'row': index, 'message': 'Party type must be customer, supplier or both'}); continue
            if row.gstin and not re.fullmatch(r'\d{2}[A-Z0-9]{13}', row.gstin.upper()):
                errors.append({'row': index, 'message': 'GSTIN must contain 15 characters'}); continue
            if row.email.strip() and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', row.email.strip()):
                errors.append({'row': index, 'message': 'Enter a valid email'}); continue
            data = {'party_type': row.party_type, 'gstin': row.gstin.upper(), 'address': row.address, 'phone': row.phone.strip(), 'email': row.email.strip(), 'payment_terms_days': row.payment_terms_days}
        else:
            data = {key: data[key] for key in ('hsn', 'unit', 'sale_rate', 'purchase_rate', 'gst_rate', 'track_stock','barcode','item_type','tax_treatment','image_data_url','image_thumbnail','low_stock_threshold')}
        seen.add(key)
        ready.append((name, data))
    result = {'dry_run': body.dry_run, 'ready': len(ready), 'duplicates': duplicates, 'errors': errors}
    if body.dry_run: return result
    if errors: raise HTTPException(422, {'message': 'Resolve import errors before saving', **result})
    for name, data in ready: session.add(Record(company_id=company_id, kind=body.kind, name=name, data=data))
    audit(session, company_id, user, 'masters.imported', body.kind, company_id, {'created': len(ready), 'duplicates': duplicates})
    session.commit()
    return {**result, 'created': len(ready)}

@app.put('/api/companies/{company_id}/masters/{master_id}')
def update_master(company_id: str, master_id: str, body: MasterRow,
                  user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    validate_item_image(body)
    master = session.scalar(select(Record).where(Record.company_id == company_id,
        Record.id == master_id, Record.kind.in_(['party', 'item'])))
    if not master: raise HTTPException(404, 'Party or item not found')
    validate_master_defaults(body, master.kind)
    if body.name.strip() != master.name: raise HTTPException(422, 'Names cannot be changed after creation')
    if master.kind == 'party':
        if body.party_type not in {'customer', 'supplier', 'both'}: raise HTTPException(422, 'Choose a valid party type')
        if body.gstin and not re.fullmatch(r'\d{2}[A-Z0-9]{13}', body.gstin.upper()): raise HTTPException(422, 'GSTIN must contain 15 characters')
        if body.email.strip() and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', body.email.strip()): raise HTTPException(422, 'Enter a valid email')
        master.data = {**(master.data or {}), 'party_type': body.party_type, 'gstin': body.gstin.upper(), 'address': body.address,
                       'phone': body.phone.strip(), 'email': body.email.strip()}
        if 'payment_terms_days' in body.model_fields_set:master.data={**master.data,'payment_terms_days':body.payment_terms_days}
    else:
        if body.track_stock != bool(master.data.get('track_stock', False)):
            raise HTTPException(422, 'Stock tracking cannot be changed after item creation')
        values = body.model_dump(mode='json')
        master.data = {**(master.data or {}), **{key: values[key] for key in ('hsn', 'unit', 'sale_rate', 'purchase_rate', 'gst_rate', 'track_stock','barcode','item_type','tax_treatment','image_data_url','image_thumbnail','low_stock_threshold') if key not in {'image_data_url','image_thumbnail','low_stock_threshold'} or key in body.model_fields_set}}
    audit(session, company_id, user, 'master.updated', master.kind, master.id)
    if master.kind == 'item' and hasattr(sys.modules[__name__], 'commerce_stock_changed'): commerce_stock_changed(company_id, session)
    session.commit(); session.refresh(master)
    return obj(master)

@app.post('/api/companies/{company_id}/records')
def create_record(company_id: str, body: RecordInput, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    return save_record(company_id, body, request, user, session)

def save_record(company_id, body, request, user, session, *, commit=True):
    """Post inside the caller transaction when processing a durable integration event."""
    company = lock_company(company_id, user, session)
    if body.kind not in KINDS: raise HTTPException(422, 'Unsupported record type')
    idempotency_key = request.headers.get('Idempotency-Key', '').strip()
    if len(idempotency_key) > 80: raise HTTPException(422, 'Idempotency key is too long')
    request_hash = hashlib.sha256(json.dumps(body.model_dump(mode='json'), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if idempotency_key:
        previous = session.scalar(select(IdempotencyKey).where(IdempotencyKey.company_id == company_id, IdempotencyKey.key == idempotency_key))
        if previous:
            if previous.request_hash != request_hash: raise HTTPException(409, 'Idempotency key was used for a different request')
            existing = session.get(Record, previous.record_id)
            return {**obj(existing), 'posted': bool(session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id, RecordPosting.record_id == existing.id)))}
    data, amount = body.data, money(body.amount)
    if body.kind in {'payment_in','payment_out','bank_transfer'}:
        data={k:v for k,v in data.items() if k not in {'advance_tax','advance_tax_released','advance_tax_event','advance_taxable','lines','cgst','sgst','igst','taxable','taxable_supply_value','tax_mode','pending_input_cgst','pending_input_sgst','pending_input_igst','round_off'}}
        data.update(cgst='0',sgst='0',igst='0',lines=[],round_off='0',advance_tax_event=False)
    if body.kind in DOCUMENTS|POSTED_KINDS:
        party=session.scalar(select(Record).where(Record.company_id==company_id,Record.kind=='party',func.lower(Record.name)==body.name.strip().lower()))
        if data.get('party_id') and (not party or data['party_id']!=party.id):raise HTTPException(422,'Party identity does not match this company and name')
        if party:
            body.name=party.name;data={**{key:party.data.get(source,'') for key,source in [('party_address','address'),('party_gstin','gstin'),('party_phone','phone')]},**data,'party_id':party.id}
    if body.kind in {'sales_invoice', 'purchase_bill'} and data.get('due_date') not in (None, ''):
        try:
            raw_due = data['due_date']
            if not isinstance(raw_due, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw_due): raise ValueError()
            due = DateType.fromisoformat(raw_due)
        except ValueError:
            raise HTTPException(422, 'Enter a valid due date in YYYY-MM-DD format')
        if due < body.date: raise HTTPException(422, 'Due date cannot be before the document date')
    if body.kind in {'party', 'item'}:
        try: master = MasterRow.model_validate({**data, 'name': body.name})
        except ValidationError: raise HTTPException(422, 'Invalid party or item details')
        validate_item_image(master)
        validate_master_defaults(master, body.kind)
        if not master.name.strip(): raise HTTPException(422, 'Name is required')
        if session.scalar(select(Record.id).where(Record.company_id == company_id, Record.kind == body.kind, func.lower(Record.name) == master.name.strip().lower())):
            raise HTTPException(409, 'A party or item with this name already exists')
        if body.kind == 'party':
            if master.party_type not in {'customer', 'supplier', 'both'}: raise HTTPException(422, 'Party type must be customer, supplier or both')
            if master.gstin and not re.fullmatch(r'\d{2}[A-Z0-9]{13}', master.gstin.upper()): raise HTTPException(422, 'GSTIN must contain 15 characters')
            if master.email.strip() and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', master.email.strip()): raise HTTPException(422, 'Enter a valid email')
            data = {'party_type': master.party_type, 'gstin': master.gstin.upper(), 'address': master.address, 'phone': master.phone.strip(), 'email': master.email.strip(), 'payment_terms_days': master.payment_terms_days}
        else:
            data = {key: value for key, value in master.model_dump(mode='json').items() if key in {'hsn', 'unit', 'sale_rate', 'purchase_rate', 'gst_rate', 'track_stock','barcode','item_type','tax_treatment','image_data_url','image_thumbnail','low_stock_threshold'}}
        body.name = master.name.strip()
    profile = session.get(CompanyTaxProfile, company_id)
    tax_mode = profile.mode if profile else 'regular'
    if tax_mode in {'regular','composition'} and body.kind in {'sales_invoice','pos','credit_note'} and not company.gstin:raise HTTPException(422,'Add the company GSTIN in Settings before issuing registered documents')
    if body.kind in DOCUMENTS and (body.kind != 'expense' or data.get('lines')):
        data, amount = calculate(data, company, tax_mode, body.kind, session)
        data = {**data, 'company_snapshot': company_obj(company, session), 'document_branding': branding_for(company_id, session)}
    if body.kind == 'expense' and not data.get('lines'):
        # Amount-only expenses have no reviewed supplier-tax lines. Ignore stale
        # or forged calculated fields rather than posting unsupported input tax.
        data = {**data, **{key: '0' for key in ('cgst', 'sgst', 'igst', 'supplier_tax',
            'pending_input_cgst', 'pending_input_sgst', 'pending_input_igst',
            'input_tax_ineligible', 'round_off')}, 'lines': [], 'taxable': str(amount)}
    if body.kind == 'pos':
        try: tender = money(data.get('tender_amount',amount))
        except (ValueError,TypeError,InvalidOperation): raise HTTPException(422,'Enter valid cash tendered')
        if not tender.is_finite() or tender < amount: raise HTTPException(422,'Tendered amount must cover the sale')
        data={**data,'tender_amount':str(tender),'change_amount':str(tender-amount if data.get('payment_account','cash')=='cash' else Decimal('0'))}
    if not amount.is_finite() or amount < 0: raise HTTPException(422, 'Amount must be finite and nonnegative')
    if body.kind in POSTED_KINDS:
        require_open_period(company_id, body.date, session)
        if not body.name.strip(): raise HTTPException(422, 'Party or description is required')
        if amount <= 0: raise HTTPException(422, 'Posted transaction amount must be greater than zero')
        if data.get('payment_account', 'cash') not in {'cash', 'bank'}: raise HTTPException(422, 'Payment account must be cash or bank')
        if body.kind == 'bank_transfer' or data.get('payment_account') == 'bank':
            bank_account_for(company_id, data.get('bank_account_id', 'default'), session)
        elif data.get('bank_account_id') not in (None, '', 'default'):
            raise HTTPException(422, 'Bank account can only be selected for bank payments')
    number = body.number.strip()
    if body.kind in NUMBERED_KINDS:
        if not number: number = next_document_number(company_id, body.kind, body.date, session)
        if len(number) > 16: raise HTTPException(422, 'Document number cannot exceed 16 characters')
    if number and session.scalar(select(Record).where(Record.company_id == company_id, Record.kind == body.kind, Record.number == number)): raise HTTPException(409, 'Document number already exists')
    conversion_source = None
    source_id = data.get('source_document_id')
    if source_id:
        if not isinstance(source_id, str): raise HTTPException(422, 'Invalid source document')
        allowed_sources = {'sales_invoice': {'estimate', 'proforma', 'sales_order'}, 'sales_order': {'estimate', 'proforma'}, 'purchase_bill': {'purchase_order'}}
        if body.kind not in allowed_sources: raise HTTPException(422, 'This document type cannot be converted')
        conversion_source = session.scalar(select(Record).where(Record.company_id == company_id, Record.id == source_id, Record.kind.in_(allowed_sources[body.kind])))
        if not conversion_source: raise HTTPException(422, 'Choose a matching source document in this company')
        if conversion_source.name.strip().casefold() != body.name.strip().casefold(): raise HTTPException(422, 'Conversion party must match the source document')
        if body.date < conversion_source.date: raise HTTPException(422, 'Conversion date cannot precede its source document')
        if conversion_source.data.get('vyapar_converted'): raise HTTPException(409, 'This source document was already converted in Vyapar')
        if session.scalar(select(DocumentConversion.id).where(DocumentConversion.company_id == company_id, DocumentConversion.source_record_id == source_id)):
            raise HTTPException(409, 'Source document has already been converted')
    target = None
    allocations = []
    if data.get('is_advance'):
        if data['is_advance'] is not True or body.kind not in {'payment_in', 'payment_out'}:
            raise HTTPException(422, 'Advance is supported only for receipts and payouts')
        data=prepare_advance_tax(sys.modules[__name__],data,company,tax_mode,body.kind,amount)
        if data.get('allocations') or data.get('applied_to'): raise HTTPException(422, 'An advance cannot have invoice allocations at creation')
    if body.kind in {'credit_note', 'debit_note'}:
        target = session.scalar(select(Record).where(Record.company_id == company_id, Record.id == data.get('applied_to'), Record.kind.in_(['sales_invoice','pos'] if body.kind=='credit_note' else ['purchase_bill'])))
        if not target or not session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id, RecordPosting.record_id == target.id)):
            raise HTTPException(422, 'Choose a posted source invoice or bill in this company')
        if target.name.strip().casefold() != body.name.strip().casefold(): raise HTTPException(422, 'Party must match the source document')
        if body.date < target.date: raise HTTPException(422, 'Note date cannot precede its source document')
        previous_notes = list(session.scalars(select(Record).where(Record.company_id == company_id, Record.kind == body.kind)))
        previous_notes = [note for note in previous_notes if note.data.get('applied_to') == target.id]
        if amount + sum((note.amount for note in previous_notes), Decimal('0')) > target.amount:
            raise HTTPException(422, 'Notes exceed the original document amount')
        for tax_key in ('cgst', 'sgst', 'igst', 'supplier_tax'):
            reversed_tax = sum((Decimal(str(note.data.get(tax_key, 0))) for note in previous_notes), Decimal('0'))
            if Decimal(str(data.get(tax_key, 0))) + reversed_tax > Decimal(str(target.data.get(tax_key, 0))):
                raise HTTPException(422, 'Note tax exceeds the original document tax')
        settled = applied_total(company_id, target.id, session)
        offset = min(amount, max(Decimal('0'), target.amount - settled)) if target.kind!='pos' else Decimal('0')
        data = {**data, 'unallocated_credit': str(amount-offset)}
        if offset: allocations.append((target, offset))
    elif body.kind in APPLICATION_KINDS and not data.get('is_advance'):
        requested = data.get('allocations') if body.kind in {'payment_in', 'payment_out'} else None
        if requested is None: requested = [{'document_id': data.get('applied_to'), 'amount': str(amount)}]
        if not isinstance(requested, list) or not 1 <= len(requested) <= 100:
            raise HTTPException(422, 'Choose one or more invoices or bills')
        seen = set()
        for allocation in requested:
            if not isinstance(allocation, dict): raise HTTPException(422, 'Invalid payment allocation')
            target_id = allocation.get('document_id')
            if not isinstance(target_id, str) or target_id in seen: raise HTTPException(422, 'Each document must be selected once')
            seen.add(target_id)
            try:
                allocated = Decimal(str(allocation.get('amount')))
                if not allocated.is_finite() or allocated <= 0 or allocated > Decimal('9999999999999.99') or allocated.as_tuple().exponent < -2: raise ValueError()
            except (InvalidOperation, ValueError): raise HTTPException(422, 'Enter a positive allocation with at most two decimal places')
            allowed_targets = [APPLICATION_KINDS[body.kind], 'opening_receivable' if body.kind == 'payment_in' else 'opening_payable']
            selected = session.scalar(select(Record).where(Record.company_id == company_id, Record.id == target_id, Record.kind.in_(allowed_targets)))
            if not selected or not session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id, RecordPosting.record_id == selected.id)):
                raise HTTPException(422, 'Choose a posted invoice or bill in this company')
            if selected.name.strip().casefold() != body.name.strip().casefold(): raise HTTPException(422, 'Party must match every selected invoice or bill')
            if body.date < selected.date: raise HTTPException(422, 'Payment or note date cannot be before the linked invoice or bill date')
            if applied_total(company_id, selected.id, session) + allocated > selected.amount:
                raise HTTPException(422, 'Amount exceeds the outstanding document balance')
            allocations.append((selected, allocated))
        if sum((value for _, value in allocations), Decimal('0')) != amount:
            raise HTTPException(422, 'Allocation amounts must equal the payment amount')
        target = allocations[0][0]
    if body.kind in {'purchase_bill', 'debit_note', 'sales_invoice', 'pos', 'credit_note'}:
        data = value_stock_lines(company_id, body.kind, data, tax_mode, body.date, target, session)
    if body.kind in POSTED_KINDS:data={**data,'company_snapshot':company_obj(company,session),'document_branding':branding_for(company_id,session)}
    data={**data,'created_at':datetime.now(timezone.utc).isoformat()}
    r = Record(company_id=company_id, kind=body.kind, name=body.name, number=number, date=body.date, amount=amount, data=data)
    session.add(r)
    try:
        session.flush()
        if body.kind in POSTED_KINDS:
            journal = Journal(company_id=company_id, date=body.date, reference='AUTO:' + r.id, memo=f'{body.kind} {body.number or r.id}', created_by=user.id)
            session.add(journal); session.flush()
            for key, debit, credit in posting_lines(body.kind, amount, data, tax_mode):
                session.add(JournalLine(company_id=company_id, journal_id=journal.id, account_id=posting_account(company_id, key, session), debit=debit, credit=credit))
            session.add(RecordPosting(company_id=company_id, record_id=r.id, journal_id=journal.id))
            if body.kind in {'purchase_bill', 'debit_note', 'sales_invoice', 'pos', 'credit_note'} and data.get('return_stock') is not False:
                for index, line in enumerate(data.get('lines', [])):
                    item_id = line.get('item_id')
                    if not item_id: continue
                    item = session.get(Record, item_id)
                    if not item.data.get('track_stock'): continue
                    quantity = Decimal(str(line['quantity'])) * (1 if body.kind in {'purchase_bill', 'credit_note'} else -1)
                    cost_value = Decimal(str(line['inventory_cost'])) * (1 if quantity > 0 else -1)
                    session.add(StockMovement(company_id=company_id, item_id=item_id, source_record_id=r.id,
                                              line_index=index, date=body.date, quantity=quantity, cost_value=cost_value))
                session.flush()
                tracked_items = {line.get('item_id') for line in data.get('lines', []) if line.get('item_id')}
                for item_id in tracked_items:
                    if not session.get(Record, item_id).data.get('track_stock'): continue
                    dated = session.execute(select(StockMovement.date, func.sum(StockMovement.quantity)).where(
                        StockMovement.company_id == company_id, StockMovement.item_id == item_id
                    ).group_by(StockMovement.date).order_by(StockMovement.date))
                    balance = Decimal('0')
                    for movement_date, daily_quantity in dated:
                        balance += daily_quantity
                        if balance < 0:
                            item = session.get(Record, item_id)
                            legacy_replenishment = item.data.get('vyapar_stock_migrated') and (movement_date < body.date or body.kind in {'purchase_bill', 'credit_note'})
                            if not legacy_replenishment: raise HTTPException(422, f'Insufficient stock for {item.name} on {movement_date}')
            for selected, allocated in allocations:
                allocation_class = PaymentSplitAllocation if body.kind in {'payment_in', 'payment_out'} else PaymentAllocation
                session.add(allocation_class(company_id=company_id, payment_id=r.id, document_id=selected.id, amount=allocated))
        if conversion_source:
            session.add(DocumentConversion(company_id=company_id, source_record_id=conversion_source.id, target_record_id=r.id))
        if idempotency_key:
            session.add(IdempotencyKey(company_id=company_id, key=idempotency_key, request_hash=request_hash, record_id=r.id))
        audit(session, company_id, user, 'record.posted' if body.kind in POSTED_KINDS else 'record.created', body.kind, r.id, {'number': number, 'amount': str(amount)})
        if hasattr(sys.modules[__name__], 'commerce_stock_changed'):
            commerce_stock_changed(company_id, session)
        if commit: session.commit()
        else: session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Transaction conflicts with an existing record')
    session.refresh(r)
    return {**obj(r), 'posted': body.kind in POSTED_KINDS}

@app.post('/api/companies/{company_id}/stock/opening', status_code=201)
def post_opening_stock(company_id: str, body: OpeningStockInput, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    retry_key = request.headers.get('Idempotency-Key', '').strip()
    if retry_key:
        from workflow_extensions import retry
        retry_key, request_digest, previous = retry(sys.modules[__name__], company_id, body, request, session, 'stock-opening')
        if previous: return previous
    require_open_period(company_id, body.date, session)
    item = session.scalar(select(Record).where(Record.company_id == company_id,
        Record.id == body.item_id, Record.kind == 'item'))
    if not item or not item.data.get('track_stock'):
        raise HTTPException(422, 'Choose a stock-tracked item in this company')
    if session.scalar(select(StockMovement.id).where(StockMovement.company_id == company_id,
        StockMovement.item_id == item.id)):
        raise HTTPException(409, 'Opening stock must be posted before other movements for this item')
    amount = money(body.quantity * body.unit_cost)
    if amount <= 0 or amount > Decimal('9999999999999.99'):
        raise HTTPException(422, 'Opening stock value is outside the supported range')
    record = Record(company_id=company_id, kind='stock_opening', name=item.name, date=body.date,
        amount=amount, data={'item_id': item.id, 'quantity': str(body.quantity),
                             'unit_cost': str(body.unit_cost), 'unit': item.data.get('unit', '')})
    session.add(record)
    try:
        session.flush()
        record.number = 'OPEN-' + record.id[:8].upper()
        journal = Journal(company_id=company_id, date=body.date, reference='AUTO:' + record.id,
                          memo=f'Opening stock {item.name}', created_by=user.id)
        session.add(journal); session.flush()
        session.add(JournalLine(company_id=company_id, journal_id=journal.id,
            account_id=system_account(company_id, 'inventory', session), debit=amount, credit=Decimal('0')))
        session.add(JournalLine(company_id=company_id, journal_id=journal.id,
            account_id=system_account(company_id, 'opening_equity', session), debit=Decimal('0'), credit=amount))
        session.add(RecordPosting(company_id=company_id, record_id=record.id, journal_id=journal.id))
        session.add(StockMovement(company_id=company_id, item_id=item.id, source_record_id=record.id,
                                  line_index=0, date=body.date, quantity=body.quantity, cost_value=amount))
        audit(session, company_id, user, 'stock.opening_posted', 'item', item.id,
              {'quantity': str(body.quantity), 'value': str(amount), 'record_id': record.id})
        if hasattr(sys.modules[__name__], 'commerce_stock_changed'): commerce_stock_changed(company_id, session)
        if retry_key:
            session.add(IdempotencyKey(company_id=company_id, key=retry_key, request_hash=request_digest, record_id=record.id))
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Opening stock conflicts with an existing entry')
    return {**obj(record), 'posted': True}

@app.post('/api/companies/{company_id}/stock/adjustments', status_code=201)
def post_stock_adjustment(company_id: str, body: StockAdjustmentInput, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    retry_key = request.headers.get('Idempotency-Key', '').strip()
    if retry_key:
        from workflow_extensions import retry
        retry_key, request_digest, previous = retry(sys.modules[__name__], company_id, body, request, session, 'stock-adjustment')
        if previous: return previous
    require_open_period(company_id, body.date, session)
    if body.direction not in {'increase', 'decrease'} or not body.reason.strip():
        raise HTTPException(422, 'Choose an adjustment direction and provide a reason')
    if (body.direction == 'increase') != (body.unit_cost is not None):
        raise HTTPException(422, 'Unit cost is required only when adding stock')
    item = session.scalar(select(Record).where(Record.company_id == company_id,
        Record.id == body.item_id, Record.kind == 'item'))
    if not item or not item.data.get('track_stock'):
        raise HTTPException(422, 'Choose a stock-tracked item in this company')
    movements = list(session.scalars(select(StockMovement).where(
        StockMovement.company_id == company_id, StockMovement.item_id == item.id
    ).order_by(StockMovement.date, StockMovement.id)))
    if any(m.cost_value is None for m in movements):
        raise HTTPException(409, f'{item.name} has older unvalued stock movements; migrate them before adjusting')
    if movements and body.date < movements[-1].date:
        raise HTTPException(409, 'Stock adjustments cannot be backdated before the last movement')
    held_qty = sum((m.quantity for m in movements), Decimal('0'))
    held_value = sum((m.cost_value for m in movements), Decimal('0'))
    if body.direction == 'decrease':
        if body.quantity > held_qty:
            raise HTTPException(422, f'Insufficient stock for {item.name}')
        if hasattr(sys.modules[__name__], 'commerce_assert_available'):
            commerce_assert_available(company_id, item.id, body.quantity, held_qty, session)
        amount = held_value if body.quantity == held_qty else money(held_value * body.quantity / held_qty)
        quantity, cost_value = -body.quantity, -amount
        debit_key, credit_key = 'inventory_loss', 'inventory'
    else:
        if held_qty < 0: raise HTTPException(409, 'Replenish negative legacy stock with a purchase bill or a return against its original invoice')
        if held_qty + body.quantity > Decimal('999999999999.999'):
            raise HTTPException(422, 'Stock quantity exceeds the supported range')
        amount = money(body.quantity * body.unit_cost)
        quantity, cost_value = body.quantity, amount
        debit_key, credit_key = 'inventory', 'inventory_gain'
    if amount <= 0 or amount > Decimal('9999999999999.99'):
        raise HTTPException(422, 'Adjustment value is outside the supported range')
    record = Record(company_id=company_id, kind='stock_adjustment', name=item.name, date=body.date,
        amount=amount, data={'item_id': item.id, 'direction': body.direction,
            'quantity': str(body.quantity), 'cost_value': str(amount),
            'unit_cost': str(body.unit_cost) if body.unit_cost is not None else None,
            'reason': body.reason.strip(), 'unit': item.data.get('unit', '')})
    session.add(record)
    try:
        session.flush()
        record.number = 'ADJ-' + record.id[:8].upper()
        journal = Journal(company_id=company_id, date=body.date, reference='AUTO:' + record.id,
                          memo=f'Stock {body.direction}: {item.name} — {body.reason.strip()}'[:500], created_by=user.id)
        session.add(journal); session.flush()
        session.add(JournalLine(company_id=company_id, journal_id=journal.id,
            account_id=system_account(company_id, debit_key, session), debit=amount, credit=Decimal('0')))
        session.add(JournalLine(company_id=company_id, journal_id=journal.id,
            account_id=system_account(company_id, credit_key, session), debit=Decimal('0'), credit=amount))
        session.add(RecordPosting(company_id=company_id, record_id=record.id, journal_id=journal.id))
        session.add(StockMovement(company_id=company_id, item_id=item.id, source_record_id=record.id,
                                  line_index=0, date=body.date, quantity=quantity, cost_value=cost_value))
        audit(session, company_id, user, 'stock.adjustment_posted', 'item', item.id,
              {'direction': body.direction, 'quantity': str(body.quantity),
               'value': str(amount), 'record_id': record.id})
        if hasattr(sys.modules[__name__], 'commerce_stock_changed'): commerce_stock_changed(company_id, session)
        if retry_key:
            session.add(IdempotencyKey(company_id=company_id, key=retry_key, request_hash=request_digest, record_id=record.id))
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Stock adjustment conflicts with an existing entry')
    return {**obj(record), 'posted': True}

@app.get('/api/companies/{company_id}/accounts')
def list_accounts(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    accounts = session.scalars(select(LedgerAccount).where(LedgerAccount.company_id == company_id).order_by(LedgerAccount.code))
    return [{'id': a.id, 'code': a.code, 'name': a.name, 'category': a.category} for a in accounts]

@app.get('/api/companies/{company_id}/bank-accounts')
def list_bank_accounts(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    rows = session.scalars(select(BankAccount).where(BankAccount.company_id == company_id).order_by(BankAccount.name))
    return [{'id': 'default', 'name': 'Bank clearing (legacy)', 'account_hint': '', 'ledger_code': SYSTEM_ACCOUNTS['bank'][0]}] + [
        {'id': row.id, 'name': row.name, 'account_hint': row.account_hint, 'ledger_code': session.get(LedgerAccount, row.ledger_account_id).code}
        for row in rows]

@app.post('/api/companies/{company_id}/bank-accounts', status_code=201)
def create_bank_account(company_id: str, body: BankAccountInput, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    name = body.name.strip()
    if not name: raise HTTPException(422, 'Bank account name is required')
    bank_id = str(uuid4())
    ledger = LedgerAccount(company_id=company_id, code='BANK-' + bank_id.replace('-', '')[:20], name=name, category='asset')
    session.add(ledger)
    try:
        session.flush()
        bank = BankAccount(id=bank_id, company_id=company_id, ledger_account_id=ledger.id, name=name, account_hint=body.account_hint.strip())
        session.add(bank)
        audit(session, company_id, user, 'bank_account.created', 'bank_account', bank_id, {'name': name})
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Bank account name already exists')
    return {'id': bank_id, 'name': name, 'account_hint': bank.account_hint, 'ledger_code': ledger.code}

@app.post('/api/companies/{company_id}/accounts', status_code=201)
def create_account(company_id: str, body: AccountInput, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    if body.category not in {'asset', 'liability', 'equity', 'income', 'expense'}: raise HTTPException(422, 'Invalid account category')
    if not body.name.strip(): raise HTTPException(422, 'Account name is required')
    if body.code.upper().startswith('SYS-'): raise HTTPException(422, 'SYS- account codes are reserved')
    account = LedgerAccount(company_id=company_id, code=body.code, name=body.name.strip(), category=body.category)
    session.add(account)
    try:
        session.flush()
        audit(session, company_id, user, 'account.created', 'account', account.id, {'code': account.code})
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Account code already exists')
    return {'id': account.id, 'code': account.code, 'name': account.name, 'category': account.category}

@app.post('/api/companies/{company_id}/journals', status_code=201)
def create_journal(company_id: str, body: JournalInput, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    require_open_period(company_id, body.date, session)
    reference = body.reference.strip()
    if not reference: raise HTTPException(422, 'Reference is required')
    if any((line.debit > 0) == (line.credit > 0) for line in body.lines): raise HTTPException(422, 'Each line needs either a debit or a credit')
    if sum((line.debit for line in body.lines), Decimal(0)) != sum((line.credit for line in body.lines), Decimal(0)): raise HTTPException(422, 'Journal debits and credits must balance')
    account_ids = {line.account_id for line in body.lines}
    available = set(session.scalars(select(LedgerAccount.id).where(LedgerAccount.company_id == company_id, LedgerAccount.id.in_(account_ids))))
    if available != account_ids: raise HTTPException(422, 'Every account must belong to this company')
    if session.scalar(select(LedgerAccount.id).where(LedgerAccount.company_id == company_id,
            LedgerAccount.id.in_(account_ids), LedgerAccount.code == SYSTEM_ACCOUNTS['inventory'][0])):
        raise HTTPException(422, 'Tracked inventory is updated by linked stock documents only')
    journal = Journal(company_id=company_id, date=body.date, reference=reference, memo=body.memo, created_by=user.id)
    session.add(journal)
    try:
        session.flush()
        for line in body.lines:
            session.add(JournalLine(company_id=company_id, journal_id=journal.id, account_id=line.account_id, debit=line.debit, credit=line.credit))
        audit(session, company_id, user, 'journal.created', 'journal', journal.id, {'reference': reference})
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Journal reference already exists')
    return {'id': journal.id, 'date': journal.date.isoformat(), 'reference': journal.reference, 'memo': journal.memo}

@app.get('/api/companies/{company_id}/journals')
def list_journals(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    entries = list(session.scalars(select(Journal).where(Journal.company_id == company_id).order_by(Journal.date.desc(), Journal.id)))
    links = list(session.scalars(select(JournalReversal).where(JournalReversal.company_id == company_id)))
    originals = {link.original_id: link.reversal_id for link in links}
    reversals = {link.reversal_id: link.original_id for link in links}
    source = {p.journal_id: p.record_id for p in session.scalars(select(RecordPosting).where(RecordPosting.company_id == company_id))}
    return [{'id': j.id, 'date': j.date.isoformat(), 'reference': j.reference, 'memo': j.memo, 'source_record_id': source.get(j.id), 'reversed_by': originals.get(j.id), 'reversal_of': reversals.get(j.id), 'lines': [{'account_id': l.account_id, 'debit': str(l.debit), 'credit': str(l.credit)} for l in session.scalars(select(JournalLine).where(JournalLine.company_id == company_id, JournalLine.journal_id == j.id))]} for j in entries]

@app.post('/api/companies/{company_id}/journals/{journal_id}/reverse', status_code=201)
def reverse_journal(company_id: str, journal_id: str, body: ReversalInput, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    require_open_period(company_id, body.date, session)
    original = session.scalar(select(Journal).where(Journal.company_id == company_id, Journal.id == journal_id))
    if not original: raise HTTPException(404, 'Journal not found')
    if session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id, RecordPosting.journal_id == journal_id)):
        raise HTTPException(409, 'Reverse source documents through their document workflow')
    if body.date < original.date: raise HTTPException(422, 'Reversal date cannot precede the original entry')
    if not body.reference.strip() or not body.reason.strip(): raise HTTPException(422, 'Reference and reason are required')
    if session.scalar(select(JournalReversal).where(JournalReversal.company_id == company_id, (JournalReversal.original_id == journal_id) | (JournalReversal.reversal_id == journal_id))):
        raise HTTPException(409, 'Journal is already reversed or is itself a reversal')
    lines = list(session.scalars(select(JournalLine).where(JournalLine.company_id == company_id, JournalLine.journal_id == journal_id)))
    reversal = Journal(company_id=company_id, date=body.date, reference=body.reference.strip(), memo=body.reason.strip(), created_by=user.id)
    session.add(reversal)
    try:
        session.flush()
        session.add(JournalReversal(company_id=company_id, original_id=journal_id, reversal_id=reversal.id))
        for line in lines:
            session.add(JournalLine(company_id=company_id, journal_id=reversal.id, account_id=line.account_id, debit=line.credit, credit=line.debit))
        audit(session, company_id, user, 'journal.reversed', 'journal', reversal.id, {'original_id': journal_id, 'reason': body.reason.strip()})
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Reference already exists or journal was already reversed')
    return {'id': reversal.id, 'reference': reversal.reference, 'reversal_of': journal_id}

@app.get('/api/companies/{company_id}/period-lock')
def get_period_lock(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    period = session.get(PeriodLock, company_id)
    return {'locked_through': period.locked_through.isoformat() if period else None}

@app.put('/api/companies/{company_id}/period-lock')
def set_period_lock(company_id: str, body: LockInput, user: User = Depends(current_user), session: Session = Depends(db)):
    company = lock_company(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can lock accounting periods')
    period = session.get(PeriodLock, company_id)
    if period and body.locked_through < period.locked_through: raise HTTPException(409, 'The lock date cannot be moved backwards')
    if period: period.locked_through = body.locked_through
    else: session.add(PeriodLock(company_id=company_id, locked_through=body.locked_through))
    audit(session, company_id, user, 'period.locked', 'company', company_id, {'locked_through': body.locked_through.isoformat()})
    session.commit()
    return {'locked_through': body.locked_through.isoformat()}

@app.get('/api/companies/{company_id}/trial-balance')
def trial_balance(company_id: str, through: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    accounts = list(session.scalars(select(LedgerAccount).where(LedgerAccount.company_id == company_id).order_by(LedgerAccount.code)))
    totals = {a.id: Decimal('0') for a in accounts}
    rows = session.execute(select(JournalLine.account_id, JournalLine.debit, JournalLine.credit).join(Journal, (Journal.id == JournalLine.journal_id) & (Journal.company_id == JournalLine.company_id)).where(Journal.company_id == company_id, Journal.date <= through))
    for account_id, debit, credit in rows: totals[account_id] += debit - credit
    result = [{'id': a.id, 'code': a.code, 'name': a.name, 'category': a.category, 'debit': str(max(totals[a.id], Decimal('0'))), 'credit': str(max(-totals[a.id], Decimal('0')))} for a in accounts]
    return {'through': through.isoformat(), 'accounts': result, 'total_debit': str(sum((max(value, Decimal('0')) for value in totals.values()), Decimal('0'))), 'total_credit': str(sum((max(-value, Decimal('0')) for value in totals.values()), Decimal('0')))}

def account_movements(company_id, from_date, to_date, session):
    accounts = list(session.scalars(select(LedgerAccount).where(LedgerAccount.company_id == company_id).order_by(LedgerAccount.code)))
    totals = {a.id: Decimal('0') for a in accounts}
    rows = session.execute(select(JournalLine.account_id, JournalLine.debit, JournalLine.credit)
        .join(Journal, (Journal.id == JournalLine.journal_id) & (Journal.company_id == JournalLine.company_id))
        .where(Journal.company_id == company_id, Journal.date >= from_date, Journal.date <= to_date))
    for account_id, debit, credit in rows: totals[account_id] += debit - credit
    return accounts, totals

@app.get('/api/companies/{company_id}/reports/financial')
def financial_report(company_id: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    accounts, period = account_movements(company_id, from_date, to_date, session)
    _, cumulative = account_movements(company_id, DateType(1900, 1, 1), to_date, session)
    rows = [{'code': a.code, 'name': a.name, 'category': a.category,
             'period_balance': str(period[a.id] if a.category in {'asset', 'expense'} else -period[a.id]),
             'closing_balance': str(cumulative[a.id] if a.category in {'asset', 'expense'} else -cumulative[a.id])}
            for a in accounts]
    income = sum((-period[a.id] for a in accounts if a.category == 'income'), Decimal('0'))
    expense = sum((period[a.id] for a in accounts if a.category == 'expense'), Decimal('0'))
    assets = sum((cumulative[a.id] for a in accounts if a.category == 'asset'), Decimal('0'))
    liabilities = sum((-cumulative[a.id] for a in accounts if a.category == 'liability'), Decimal('0'))
    equity = sum((-cumulative[a.id] for a in accounts if a.category == 'equity'), Decimal('0'))
    cumulative_income = sum((-cumulative[a.id] for a in accounts if a.category == 'income'), Decimal('0'))
    cumulative_expense = sum((cumulative[a.id] for a in accounts if a.category == 'expense'), Decimal('0'))
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(), 'accounts': rows,
            'income': str(income), 'expenses': str(expense), 'net_profit': str(income - expense),
            'assets': str(assets), 'liabilities': str(liabilities), 'equity': str(equity),
            'retained_earnings': str(cumulative_income - cumulative_expense),
            'balance_difference': str(assets - liabilities - equity - cumulative_income + cumulative_expense)}

@app.get('/api/companies/{company_id}/reports/parties')
def party_report(company_id: str, from_date: DateType, to_date: DateType, party: str = Query(default='', max_length=120), user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    postings = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    kinds = {'sales_invoice', 'credit_note', 'payment_in', 'purchase_bill', 'debit_note', 'payment_out', 'advance_application','opening_receivable','opening_payable','credit_application','customer_refund','supplier_refund'}
    records = list(session.scalars(select(Record).where(Record.company_id == company_id, Record.id.in_(postings), Record.kind.in_(kinds), Record.date <= to_date).order_by(Record.date, Record.number, Record.id)))
    selected = party.strip().casefold()
    records = [r for r in records if not selected or r.name.strip().casefold() == selected]
    receivable = payable = Decimal('0')
    opening_receivable = opening_payable = Decimal('0')
    rows = []
    for r in records:
        if r.data.get('is_advance'): continue
        if r.kind in {'sales_invoice','opening_receivable'}: receivable += r.amount
        elif r.kind in {'credit_note', 'payment_in'}: receivable -= r.amount - Decimal(str(r.data.get('unallocated_credit',0)))
        elif r.kind in {'purchase_bill','opening_payable'}: payable += r.amount
        elif r.kind in {'advance_application','credit_application'} and r.data.get('payment_kind') == 'payment_in': receivable -= r.amount
        elif r.kind in {'advance_application','credit_application'}: payable -= r.amount
        elif r.kind in {'debit_note','payment_out'}: payable -= r.amount - Decimal(str(r.data.get('unallocated_credit',0)))
        if r.date < from_date:
            opening_receivable, opening_payable = receivable, payable
        else:
            rows.append({'date': r.date.isoformat(), 'party': r.name, 'kind': r.kind, 'number': r.number,
                         'amount': str(r.amount), 'receivable': str(receivable), 'payable': str(payable)})
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(), 'party': party.strip(),
            'opening_receivable': str(opening_receivable), 'opening_payable': str(opening_payable),
            'closing_receivable': str(receivable), 'closing_payable': str(payable), 'rows': rows}

@app.get('/api/companies/{company_id}/reports/advances')
def advances_report(company_id: str, as_of: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    posted = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    records = list(session.scalars(select(Record).where(Record.company_id == company_id, Record.id.in_(posted), Record.date <= as_of,
        Record.kind.in_(['payment_in', 'payment_out', 'advance_application','advance_refund'])).order_by(Record.date, Record.number, Record.id)))
    used = {}
    for r in records:
        if r.kind in {'advance_application','advance_refund'}: used[r.data.get('advance_id')] = used.get(r.data.get('advance_id'), Decimal('0')) + r.amount
    rows = [{'id': r.id, 'date': r.date.isoformat(), 'number': r.number, 'party': r.name,
        'side': 'customer' if r.kind == 'payment_in' else 'supplier', 'amount': str(r.amount),
        'applied': str(used.get(r.id, Decimal('0'))), 'available': str(r.amount - used.get(r.id, Decimal('0')))}
        for r in records if r.kind in {'payment_in', 'payment_out'} and r.data.get('is_advance')]
    return {'as_of': as_of.isoformat(), 'rows': rows, 'totals': {side: str(sum((Decimal(r['available']) for r in rows if r['side'] == side), Decimal('0'))) for side in ('customer', 'supplier')}}

@app.get('/api/companies/{company_id}/reports/advances.{fmt}')
def advances_report_export(company_id: str, fmt: str, as_of: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    report = advances_report(company_id, as_of, user, session)
    rows = [[r[key] for key in ('date', 'number', 'party', 'side', 'amount', 'applied', 'available')] for r in report['rows']]
    company = company_for(company_id, user, session)
    return export_table(company.name, 'Advances as of ' + as_of.isoformat(), ['Date', 'Reference', 'Party', 'Side', 'Original', 'Applied/refunded', 'Available'], rows, fmt, 'apex-advances')

@app.get('/api/companies/{company_id}/reports/ageing')
def ageing_report(company_id: str, as_of: DateType, party: str = Query(default='', max_length=120),
                  user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    posted = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    documents = list(session.scalars(select(Record).where(Record.company_id == company_id,
        Record.id.in_(posted), Record.kind.in_(['sales_invoice', 'purchase_bill','opening_receivable','opening_payable']), Record.date <= as_of)
        .order_by(Record.name, Record.date, Record.number, Record.id)))
    applied = dict(session.execute(select(PaymentAllocation.document_id, func.sum(PaymentAllocation.amount))
        .join(Record, (Record.id == PaymentAllocation.payment_id) & (Record.company_id == PaymentAllocation.company_id))
        .where(PaymentAllocation.company_id == company_id, Record.date <= as_of)
        .group_by(PaymentAllocation.document_id)).all())
    for document_id, value in session.execute(select(PaymentSplitAllocation.document_id, func.sum(PaymentSplitAllocation.amount))
        .join(Record, (Record.id == PaymentSplitAllocation.payment_id) & (Record.company_id == PaymentSplitAllocation.company_id))
        .where(PaymentSplitAllocation.company_id == company_id, Record.date <= as_of)
        .group_by(PaymentSplitAllocation.document_id)):
        applied[document_id] = applied.get(document_id, Decimal('0')) + value
    bucket_names = ('0-30', '31-60', '61-90', '91+')
    buckets = {side: {name: Decimal('0') for name in bucket_names} for side in ('receivable', 'payable')}
    totals = {'receivable': Decimal('0'), 'payable': Decimal('0')}
    selected = party.strip().casefold()
    rows = []
    for document in documents:
        if selected and document.name.strip().casefold() != selected: continue
        settled = applied.get(document.id, Decimal('0'))
        remaining = document.amount - settled
        if remaining <= 0: continue
        age_days = (as_of - document.date).days
        bucket = bucket_names[0 if age_days <= 30 else 1 if age_days <= 60 else 2 if age_days <= 90 else 3]
        side = 'receivable' if document.kind in {'sales_invoice','opening_receivable'} else 'payable'
        buckets[side][bucket] += remaining
        totals[side] += remaining
        try: due_date = DateType.fromisoformat(document.data.get('due_date') or '')
        except (TypeError, ValueError): due_date = None
        rows.append({'document_id': document.id, 'party': document.name, 'kind': document.kind,
            'number': document.number, 'date': document.date.isoformat(), 'age_days': age_days,
            'due_date': due_date.isoformat() if due_date else None,
            'overdue_days': max(0, (as_of - due_date).days) if due_date else None,
            'bucket': bucket, 'original_amount': str(document.amount), 'applied_amount': str(settled),
            'outstanding': str(remaining)})
    return {'as_of': as_of.isoformat(), 'party': party.strip(), 'rows': rows,
        'totals': {side: str(value) for side, value in totals.items()},
        'buckets': {side: {name: str(value) for name, value in amounts.items()} for side, amounts in buckets.items()}}

def export_table(company_name, title, headers, rows, fmt, filename):
    out = io.BytesIO()
    if fmt == 'xlsx':
        book = Workbook(); sheet = book.active; sheet.title = re.sub(r'[\\/*?:\[\]]', ' ', title)[:31] or 'Report'
        sheet.append([company_name]); sheet.append([title]); sheet.append(headers)
        if isinstance(company_name, str) and company_name.startswith('='): sheet['A1'].data_type = 's'
        text_columns = {'Name', 'Description', 'Code', 'HSN', 'HSN / SAC', 'GSTIN', 'Phone', 'Email', 'Number', 'Document', 'Date', 'Type', 'Party', 'Account', 'Unit', 'Bucket', 'Category', 'Item', 'Reference'}
        for row in rows:
            prepared = []
            for header, value in zip(headers, row):
                if header not in text_columns and isinstance(value, str) and re.fullmatch(r'-?\d+(?:\.\d+)?', value):
                    prepared.append(float(value) if '.' in value else int(value))
                else:
                    prepared.append(value)
            sheet.append(prepared)
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value, str) and cell.value.startswith('='): cell.data_type = 's'
        sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
        sheet['A1'].font = Font(name='Calibri', size=16, bold=True, color='244F43')
        sheet['A2'].font = Font(name='Calibri', size=11, color='52605B')
        for cell in sheet[3]:
            cell.fill = PatternFill('solid', fgColor='244F43')
            cell.font = Font(name='Calibri', bold=True, color='FFFFFF')
            cell.alignment = Alignment(vertical='center')
        sheet.row_dimensions[3].height = 24
        for row in sheet.iter_rows(min_row=4):
            for cell in row:
                if isinstance(cell.value, (int, float)):
                    cell.number_format = '#,##0.00' if isinstance(cell.value, float) else '0'
                    cell.alignment = Alignment(horizontal='right')
                if cell.row % 2 == 0:
                    cell.fill = PatternFill('solid', fgColor='F5F8F5')
        sheet.freeze_panes = 'A4'
        sheet.sheet_view.showGridLines = False
        sheet.auto_filter.ref = f'A3:{sheet.cell(3, len(headers)).column_letter}{sheet.max_row}'
        for column_index, column in enumerate(sheet.columns, start=1):
            letter = sheet.cell(3, column_index).column_letter
            sheet.column_dimensions[letter].width = min(42, max(14, max((len(str(cell.value or '')) for cell in column), default=14) + 2))
        book.save(out)
        media = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif fmt == 'pdf':
        from html import escape
        page = landscape(A4) if len(headers) > 6 else A4
        width = page[0] - 50
        first = min(145, width * .27)
        column_widths = [first] + [(width - first) / (len(headers) - 1)] * (len(headers) - 1)
        body_style = ParagraphStyle('ReportCell', fontName='Helvetica', fontSize=7, leading=9)
        heading_style = ParagraphStyle('ReportHeading', parent=body_style, fontName='Helvetica-Bold', textColor=colors.white)
        def cell(value, style): return Paragraph(escape(str(value if value is not None else '')), style)
        table_rows = [[cell(value, heading_style) for value in headers]]
        table_rows += [[cell(value, body_style) for value in row] for row in rows]
        table = LongTable(table_rows, colWidths=column_widths, repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#244f43')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f8f5')]),
            ('LINEBELOW', (0, 0), (-1, -1), .2, colors.HexColor('#dde6de')), ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
        document = SimpleDocTemplate(out, pagesize=page, leftMargin=25, rightMargin=25, topMargin=30, bottomMargin=30, title=title)
        document.build([Paragraph(escape(company_name), ParagraphStyle('ReportTitle', fontName='Helvetica-Bold', fontSize=12, leading=16)),
                        Paragraph(escape(title), body_style), Spacer(1, 12), table])
        media = 'application/pdf'
    else: raise HTTPException(404, 'Unsupported export format')
    return Response(out.getvalue(), media_type=media, headers={'Content-Disposition': f'attachment; filename="{filename}.{fmt}"'})

@app.get('/api/companies/{company_id}/masters/export.{fmt}')
def export_masters(company_id: str, fmt: str, kind: str,
                   user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    if kind not in {'party', 'item'}: raise HTTPException(422, 'Choose parties or items')
    masters = list(session.scalars(select(Record).where(Record.company_id == company_id,
        Record.kind == kind).order_by(Record.name, Record.id)))
    if kind == 'party':
        headers = ['Name', 'Type', 'GSTIN', 'Phone', 'Email', 'Address']
        rows = [[r.name, r.data.get('party_type', 'both'), r.data.get('gstin', ''),
                 r.data.get('phone', ''), r.data.get('email', ''), r.data.get('address', '')] for r in masters]
    else:
        headers = ['Name', 'HSN / SAC', 'Unit', 'Sale rate', 'Purchase rate', 'GST rate', 'Stock tracked','Barcode','Item type','Tax treatment']
        rows = [[r.name, r.data.get('hsn', ''), r.data.get('unit', ''), r.data.get('sale_rate', '0'),
                 r.data.get('purchase_rate', '0'), r.data.get('gst_rate', '0'), 'Yes' if r.data.get('track_stock') else 'No',r.data.get('barcode',''),r.data.get('item_type','goods'),r.data.get('tax_treatment','taxable' if Decimal(str(r.data.get('gst_rate',0))) else 'nil_rated')] for r in masters]
    return export_table(company.name, 'Party list' if kind == 'party' else 'Item list', headers, rows, fmt, kind + '-list')

@app.get('/api/companies/{company_id}/cash-book')
def cash_book(company_id: str, from_date: DateType, to_date: DateType, bank_account_id: str = 'default',
              user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    bank = bank_account_for(company_id, bank_account_id, session)
    cash_id = session.scalar(select(LedgerAccount.id).where(LedgerAccount.company_id == company_id, LedgerAccount.code == 'SYS-CASH'))
    bank_id = bank.ledger_account_id if bank else session.scalar(select(LedgerAccount.id).where(LedgerAccount.company_id == company_id, LedgerAccount.code == 'SYS-BANK'))
    ids = [account_id for account_id in (cash_id, bank_id) if account_id]
    grouped = {}
    if ids:
        query = (select(Journal, JournalLine, Record)
            .join(JournalLine, (JournalLine.journal_id == Journal.id) & (JournalLine.company_id == Journal.company_id))
            .outerjoin(RecordPosting, (RecordPosting.journal_id == Journal.id) & (RecordPosting.company_id == Journal.company_id))
            .outerjoin(Record, (Record.id == RecordPosting.record_id) & (Record.company_id == Journal.company_id))
            .where(Journal.company_id == company_id, Journal.date <= to_date, JournalLine.account_id.in_(ids))
            .order_by(Journal.date, Journal.id, JournalLine.id))
        for journal, line, record in session.execute(query):
            if journal.id not in grouped:
                grouped[journal.id] = {'id': journal.id, 'date': journal.date,
                    'reference': record.number if record and record.number else journal.reference,
                    'description': record.name if record else journal.memo,
                    'kind': record.kind if record else 'journal', 'cash': Decimal('0'), 'bank': Decimal('0')}
            side = 'cash' if line.account_id == cash_id else 'bank'
            grouped[journal.id][side] += line.debit - line.credit
    opening = {'cash': Decimal('0'), 'bank': Decimal('0')}
    for row in grouped.values():
        if row['date'] < from_date:
            for side in opening: opening[side] += row[side]
    balances = dict(opening)
    rows = []
    for row in grouped.values():
        if row['date'] < from_date or (row['cash'] == 0 and row['bank'] == 0): continue
        for side in balances: balances[side] += row[side]
        rows.append({'id': row['id'], 'date': row['date'].isoformat(), 'reference': row['reference'],
            'description': row['description'], 'kind': row['kind'], 'cash': str(row['cash']), 'bank': str(row['bank']),
            'cash_balance': str(balances['cash']), 'bank_balance': str(balances['bank'])})
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(),
            'bank_account_id': bank_account_id, 'bank_name': bank.name if bank else 'Bank clearing',
            'opening': {key: str(value) for key, value in opening.items()},
            'closing': {key: str(value) for key, value in balances.items()}, 'rows': rows}

@app.get('/api/companies/{company_id}/cash-book.{fmt}')
def export_cash_book(company_id: str, fmt: str, from_date: DateType, to_date: DateType, bank_account_id: str = 'default',
                     user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    data = cash_book(company_id, from_date, to_date, bank_account_id, user, session)
    rows = [['', '', 'Opening balance', '', '', '', data['opening']['cash'], data['opening']['bank']]]
    rows += [[row[key] for key in ('date', 'reference', 'description', 'kind', 'cash', 'bank', 'cash_balance', 'bank_balance')] for row in data['rows']]
    rows.append(['', '', 'Closing balance', '', '', '', data['closing']['cash'], data['closing']['bank']])
    return export_table(company.name, f"Cash and {data['bank_name']} book {from_date} to {to_date}",
        ['Date', 'Reference', 'Description', 'Type', 'Cash movement', 'Bank movement', 'Cash balance', 'Bank balance'], rows, fmt, 'cash-bank-book')

@app.get('/api/companies/{company_id}/reports/financial.{fmt}')
def export_financial(company_id: str, fmt: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    data = financial_report(company_id, from_date, to_date, user, session)
    rows = [[r['code'], r['name'], r['category'], r['period_balance'], r['closing_balance']] for r in data['accounts']]
    rows += [['', 'Net profit', '', data['net_profit'], ''], ['', 'Assets', '', '', data['assets']],
             ['', 'Liabilities', '', '', data['liabilities']], ['', 'Equity and retained earnings', '', '', str(Decimal(data['equity']) + Decimal(data['retained_earnings']))]]
    return export_table(company.name, f"Financial report {from_date} to {to_date}", ['Code', 'Account', 'Category', 'Period', 'Closing'], rows, fmt, 'financial-report')

@app.get('/api/companies/{company_id}/reports/parties.{fmt}')
def export_parties(company_id: str, fmt: str, from_date: DateType, to_date: DateType, party: str = Query(default='', max_length=120), user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    data = party_report(company_id, from_date, to_date, party, user, session)
    rows = [[r[key] for key in ('date', 'party', 'kind', 'number', 'amount', 'receivable', 'payable')] for r in data['rows']]
    return export_table(company.name, f"Party statement {from_date} to {to_date}", ['Date', 'Party', 'Type', 'Number', 'Amount', 'Receivable', 'Payable'], rows, fmt, 'party-statement')

@app.get('/api/companies/{company_id}/reports/ageing.{fmt}')
def export_ageing(company_id: str, fmt: str, as_of: DateType, party: str = Query(default='', max_length=120),
                  user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    data = ageing_report(company_id, as_of, party, user, session)
    rows = [[r[key] for key in ('party', 'kind', 'number', 'date', 'age_days', 'original_amount', 'applied_amount', 'outstanding', 'bucket', 'due_date', 'overdue_days')]
            for r in data['rows']]
    rows += [['', 'Total receivable', '', '', '', '', '', data['totals']['receivable'], '', '', ''],
             ['', 'Total payable', '', '', '', '', '', data['totals']['payable'], '', '', '']]
    return export_table(company.name, f'Document ageing as of {as_of}',
        ['Party', 'Type', 'Document', 'Date', 'Age days', 'Original', 'Applied', 'Outstanding', 'Bucket', 'Due date', 'Overdue days'],
        rows, fmt, 'document-ageing')

@app.get('/api/companies/{company_id}/reports/gst')
def gst_report(company_id: str, from_date: DateType, to_date: DateType,
               user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    profile = session.get(CompanyTaxProfile, company_id)
    posted = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    kinds = ('sales_invoice','pos','credit_note','purchase_bill','debit_note','expense','payment_in','advance_application','advance_refund')
    documents = list(session.scalars(select(Record).where(Record.company_id == company_id,
        Record.id.in_(posted), Record.kind.in_(kinds), Record.date >= from_date, Record.date <= to_date)))
    regular = [record for record in documents if record.data.get('tax_mode') == 'regular' and (record.kind in DOCUMENTS or record.data.get('advance_tax_event'))]
    grouped = {}
    for record in regular:
        outward = record.kind in {'sales_invoice','pos','credit_note','payment_in','advance_application','advance_refund'}
        side = 'outward' if outward else 'inward'
        sign = -1 if record.kind in {'credit_note', 'debit_note'} else 1
        for line in record.data.get('lines', []):
            treatment = line.get('tax_treatment', 'taxable')
            rate = str(Decimal(str(line.get('gst_rate', 0))))
            key = (side, treatment, rate)
            if key not in grouped:
                grouped[key] = {'taxable': Decimal('0'), 'tax': Decimal('0'),
                                'pending_input': Decimal('0'), 'ineligible_input': Decimal('0')}
            values = grouped[key]
            taxable = Decimal(str(line.get('taxable', 0))) * sign
            tax = Decimal(str(line.get('tax', 0))) * sign
            values['taxable'] += taxable
            values['tax'] += tax
            if not outward:
                values['pending_input' if line.get('itc_treatment') == 'pending_review' else 'ineligible_input'] += tax
    rows = [{'side': side, 'treatment': treatment, 'gst_rate': rate,
             **{field: str(value) for field, value in values.items()}}
            for (side, treatment, rate), values in sorted(grouped.items(),
                key=lambda item: (item[0][0], item[0][1], Decimal(item[0][2])))]
    totals = {side: {field: str(sum((values[field] for key, values in grouped.items() if key[0] == side), Decimal('0')))
                     for field in ('taxable', 'tax', 'pending_input', 'ineligible_input')}
              for side in ('outward', 'inward')}
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(),
            'applicable': bool(profile and profile.mode == 'regular') or bool(regular),
            'rows': rows, 'totals': totals, 'document_count': len(regular),
            'note': 'Posted-document tax analysis for review; not a filed GST return.'}

@app.get('/api/companies/{company_id}/reports/gst.{fmt}')
def export_gst(company_id: str, fmt: str, from_date: DateType, to_date: DateType,
               user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    data = gst_report(company_id, from_date, to_date, user, session)
    rows = [[row['side'].title(), row['treatment'].replace('_', ' ').title(), row['gst_rate'],
             row['taxable'], row['tax'], row['pending_input'], row['ineligible_input']]
            for row in data['rows']]
    if data['applicable']:
        for side in ('outward', 'inward'):
            totals = data['totals'][side]
            rows.append([side.title() + ' total', '', '', totals['taxable'], totals['tax'],
                         totals['pending_input'], totals['ineligible_input']])
    if not data['applicable']: rows.append(['GST not applicable for this company and period', '', '', '', '', '', ''])
    return export_table(company.name, f'GST analysis {from_date} to {to_date}',
        ['Side', 'Classification', 'GST rate %', 'Supply value', 'Tax', 'Input pending review', 'Input in cost'],
        rows, fmt, 'gst-analysis')

@app.get('/api/companies/{company_id}/reports/items')
def item_report(company_id: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    postings = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    kinds = {'sales_invoice', 'pos', 'credit_note', 'purchase_bill', 'debit_note'}
    records = session.scalars(select(Record).where(Record.company_id == company_id, Record.id.in_(postings), Record.kind.in_(kinds), Record.date <= to_date))
    values = {}
    for record in records:
        for line in record.data.get('lines', []):
            name = str(line.get('description', '')).strip()
            if not name: continue
            key = (name.casefold(), str(line.get('hsn', '')).strip())
            if key not in values:
                values[key] = {'name': name, 'hsn': key[1], 'opening_quantity': Decimal('0'), 'purchased_quantity': Decimal('0'),
                               'sold_quantity': Decimal('0'), 'closing_quantity': Decimal('0'), 'purchase_value': Decimal('0'), 'sales_value': Decimal('0')}
            item = values[key]
            qty = Decimal(str(line.get('quantity', 0))) if record.data.get('return_stock') is not False else Decimal('0')
            taxable = Decimal(str(line.get('taxable', 0)))
            movement = qty if record.kind in {'purchase_bill', 'credit_note'} else -qty
            if record.date < from_date:
                item['opening_quantity'] += movement
            else:
                if record.kind == 'purchase_bill':
                    item['purchased_quantity'] += qty; item['purchase_value'] += taxable
                elif record.kind == 'debit_note':
                    item['purchased_quantity'] -= qty; item['purchase_value'] -= taxable
                elif record.kind in {'sales_invoice', 'pos'}:
                    item['sold_quantity'] += qty; item['sales_value'] += taxable
                else:
                    item['sold_quantity'] -= qty; item['sales_value'] -= taxable
            item['closing_quantity'] += movement
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(),
            'rows': [{**item, **{field: str(item[field]) for field in ('opening_quantity', 'purchased_quantity', 'sold_quantity', 'closing_quantity', 'purchase_value', 'sales_value')}}
                     for item in sorted(values.values(), key=lambda row: (row['name'].casefold(), row['hsn']))]}

@app.get('/api/companies/{company_id}/reports/items.{fmt}')
def export_items(company_id: str, fmt: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    data = item_report(company_id, from_date, to_date, user, session)
    keys = ('name', 'hsn', 'opening_quantity', 'purchased_quantity', 'sold_quantity', 'closing_quantity', 'purchase_value', 'sales_value')
    rows = [[row[key] for key in keys] for row in data['rows']]
    return export_table(company.name, f"Item activity {from_date} to {to_date}", ['Item', 'HSN/SAC', 'Opening', 'Purchased', 'Sold', 'Closing', 'Purchase value', 'Sales value'], rows, fmt, 'item-activity')

@app.get('/api/companies/{company_id}/reports/stock')
def stock_report(company_id: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    items = list(session.scalars(select(Record).where(Record.company_id == company_id, Record.kind == 'item')))
    values = {item.id: {'item_id': item.id, 'name': item.name, 'unit': item.data.get('unit', ''),
        'opening_quantity': Decimal('0'), 'introduced_quantity': Decimal('0'), 'adjustment_quantity': Decimal('0'), 'purchased_quantity': Decimal('0'), 'sold_quantity': Decimal('0'),
        'closing_quantity': Decimal('0'), 'closing_value': Decimal('0'), 'unvalued_movements': 0}
        for item in items if item.data.get('track_stock')}
    movements = session.scalars(select(StockMovement).where(StockMovement.company_id == company_id,
        StockMovement.date <= to_date).order_by(StockMovement.date, StockMovement.id))
    for movement in movements:
        row = values.get(movement.item_id)
        if row is None: continue
        if movement.cost_value is None: row['unvalued_movements'] += 1
        else: row['closing_value'] += movement.cost_value
        if movement.date < from_date: row['opening_quantity'] += movement.quantity
        else:
            source = session.get(Record, movement.source_record_id)
            if source.kind == 'stock_opening': row['introduced_quantity'] += movement.quantity
            elif source.kind == 'stock_adjustment': row['adjustment_quantity'] += movement.quantity
            elif source.kind in {'purchase_bill', 'debit_note'}: row['purchased_quantity'] += movement.quantity
            else: row['sold_quantity'] -= movement.quantity
        row['closing_quantity'] += movement.quantity
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(),
        'rows': [{**row, **{key: str(row[key]) for key in ('opening_quantity', 'introduced_quantity', 'adjustment_quantity', 'purchased_quantity', 'sold_quantity', 'closing_quantity')},
                  'closing_value': None if row['unvalued_movements'] else str(row['closing_value'])}
                 for row in sorted(values.values(), key=lambda item: item['name'].casefold())]}

@app.get('/api/companies/{company_id}/reports/stock.{fmt}')
def export_stock(company_id: str, fmt: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    data = stock_report(company_id, from_date, to_date, user, session)
    rows = [[row[key] for key in ('name', 'unit', 'opening_quantity', 'introduced_quantity', 'adjustment_quantity', 'purchased_quantity', 'sold_quantity', 'closing_quantity')]
            + [row['closing_value'] if row['closing_value'] is not None else 'Needs migration'] for row in data['rows']]
    return export_table(company.name, f"Tracked stock {from_date} to {to_date}",
        ['Item', 'Unit', 'Opening', 'Stock introduced', 'Adjustments net', 'Purchased net', 'Sold net', 'Closing', 'Closing cost value'], rows, fmt, 'tracked-stock')

@app.get('/api/companies/{company_id}/reports/register')
def transaction_register(company_id: str, from_date: DateType, to_date: DateType, group: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    if group not in {'sales','purchases','expenses'}: raise HTTPException(422, 'Choose sales, purchases or expenses')
    kinds = {'sales_invoice','pos','credit_note'} if group=='sales' else {'expense'} if group=='expenses' else {'purchase_bill','debit_note'}
    postings = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    records = session.scalars(select(Record).where(Record.company_id == company_id, Record.id.in_(postings), Record.kind.in_(kinds), Record.date >= from_date, Record.date <= to_date).order_by(Record.date, Record.number, Record.id))
    rows = []
    total = Decimal('0')
    for record in records:
        sign = -1 if record.kind in {'credit_note', 'debit_note'} else 1
        amount = sign * record.amount
        total += amount
        rows.append({'date': record.date.isoformat(), 'kind': record.kind, 'number': record.number,
                     'party': record.name, 'taxable': str(sign * Decimal(str(record.data.get('taxable', record.amount)))),
                     'cgst': str(sign * Decimal(str(record.data.get('cgst', 0)))),
                     'sgst': str(sign * Decimal(str(record.data.get('sgst', 0)))),
                     'igst': str(sign * Decimal(str(record.data.get('igst', 0)))),
                     'supplier_tax': str(sign * Decimal(str(record.data.get('supplier_tax', 0)))),
                     'input_ineligible': str(sign * Decimal(str(record.data.get('input_tax_ineligible', 0)))), 'amount': str(amount)})
    return {'group': group, 'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(), 'rows': rows, 'total': str(total)}

@app.get('/api/companies/{company_id}/reports/register.{fmt}')
def export_transaction_register(company_id: str, fmt: str, from_date: DateType, to_date: DateType, group: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    data = transaction_register(company_id, from_date, to_date, group, user, session)
    keys = ('date', 'kind', 'number', 'party', 'taxable', 'cgst', 'sgst', 'igst', 'supplier_tax', 'input_ineligible', 'amount')
    rows = [[row[key] for key in keys] for row in data['rows']]
    rows.append(['', '', '', 'Net total', '', '', '', '', '', '', data['total']])
    return export_table(company.name, f"{group.title()} register {from_date} to {to_date}", ['Date', 'Type', 'Number', 'Party', 'Subtotal', 'CGST', 'SGST', 'IGST', 'Supplier tax', 'GST in cost', 'Total'], rows, fmt, f'{group}-register')

@app.post('/api/companies/{company_id}/bank-statement/import')
def import_bank_statement(company_id: str, body: StatementImport, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    bank_account = bank_account_for(company_id, body.bank_account_id, session)
    bank_id = bank_account.id if bank_account else None
    occurrences = {};existing={}
    for day,description,reference,amount,count in session.execute(select(BankStatementLine.date,BankStatementLine.description,BankStatementLine.reference,BankStatementLine.amount,func.count(BankStatementLine.id)).where(BankStatementLine.company_id==company_id,BankStatementLine.bank_account_id==bank_id).group_by(BankStatementLine.date,BankStatementLine.description,BankStatementLine.reference,BankStatementLine.amount)):
        key=(day.isoformat(),description.strip(),reference.strip(),str(money(amount)));existing[key]=existing.get(key,0)+count
    added = duplicates = 0
    for line in body.lines:
        if line.amount == 0: raise HTTPException(422, 'Statement amount must be nonzero')
        key = (line.date.isoformat(), line.description.strip(), line.reference.strip(), str(money(line.amount)))
        occurrences[key] = occurrences.get(key, 0) + 1
        if occurrences[key] <= existing.get(key,0):
            duplicates += 1
            continue
        fingerprint_key = (*key, occurrences[key]) if bank_id is None else (bank_id, *key, occurrences[key])
        fingerprint = hashlib.sha256(repr(fingerprint_key).encode()).hexdigest()
        if not body.dry_run:session.add(BankStatementLine(company_id=company_id, bank_account_id=bank_id, date=line.date, description=line.description.strip(), reference=line.reference.strip(), amount=line.amount, fingerprint=fingerprint))
        added += 1
    if body.dry_run:return {'added':added,'duplicates':duplicates,'dry_run':True}
    if added: audit(session, company_id, user, 'bank_statement.imported', 'company', company_id, {'bank_account_id': bank_id or 'default', 'added': added, 'duplicates': duplicates})
    try: session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Concurrent import conflict; retry')
    return {'added': added, 'duplicates': duplicates}

@app.get('/api/companies/{company_id}/bank-statement')
def bank_statement(company_id: str, bank_account_id: str = 'default', as_of: DateType | None = None, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    bank_account = bank_account_for(company_id, bank_account_id, session)
    bank_id = bank_account.id if bank_account else None
    scope = BankStatementLine.bank_account_id == bank_id if bank_id else BankStatementLine.bank_account_id.is_(None)
    statement_query = select(BankStatementLine).where(BankStatementLine.company_id == company_id, scope)
    if as_of: statement_query = statement_query.where(BankStatementLine.date <= as_of)
    rows = list(session.scalars(statement_query.order_by(BankStatementLine.date.desc(), BankStatementLine.id)))
    allocations_by_line = {r.id: [] for r in rows}
    if rows:
        for allocation in session.scalars(select(BankMatchAllocation).where(
            BankMatchAllocation.company_id == company_id,
            BankMatchAllocation.statement_line_id.in_(allocations_by_line))):
            record = session.get(Record, allocation.record_id)
            allocations_by_line[allocation.statement_line_id].append({'id': allocation.id,
                'record_id': record.id, 'number': record.number, 'name': record.name, 'amount': str(allocation.amount)})
    result = []
    for line in rows:
        allocations = allocations_by_line[line.id]
        matched_amount = abs(line.amount) if line.matched_record_id else sum((Decimal(a['amount']) for a in allocations), Decimal('0'))
        result.append({'id': line.id, 'bank_account_id': line.bank_account_id or 'default',
            'date': line.date.isoformat(), 'description': line.description, 'reference': line.reference,
            'amount': str(line.amount), 'matched_record_id': line.matched_record_id,
            'matched_amount': str(matched_amount), 'remaining_amount': str(abs(line.amount) - matched_amount),
            'allocations': allocations})
    return result

def bank_record_amount(record,bank_id):
    bank_id=bank_id or 'default'
    if record.kind=='bank_transfer' and record.data.get('direction')=='bank_to_bank':
        source=record.data.get('bank_account_id') or 'default';target=record.data.get('to_bank_account_id') or 'default'
        if bank_id not in {source,target}:raise HTTPException(422,'Transfer belongs to different bank accounts')
        return record.amount if bank_id==target else -record.amount
    if (record.data.get('bank_account_id') or 'default')!=bank_id:raise HTTPException(422,'Bank transaction belongs to a different bank account')
    positive=record.kind in {'payment_in','pos','supplier_refund'} or record.kind=='advance_refund' and record.data.get('payment_kind')=='payment_out' or record.kind=='bank_transfer' and record.data.get('direction')=='cash_to_bank'
    return record.amount if positive else -record.amount

def bank_record_for_match(company_id,record_id,line,session):
    record=session.scalar(select(Record).where(Record.company_id==company_id,Record.id==record_id,Record.kind.in_(['payment_in','payment_out','expense','bank_transfer','pos','customer_refund','supplier_refund','advance_refund'])))
    if not record or (record.kind!='bank_transfer' and record.data.get('payment_account')!='bank') or not session.scalar(select(RecordPosting.id).where(RecordPosting.company_id==company_id,RecordPosting.record_id==record_id)):raise HTTPException(422,'Choose a posted bank payment in this company')
    if (bank_record_amount(record,line.bank_account_id)>0)!=(line.amount>0):raise HTTPException(422,'Statement and transaction directions differ')
    return record

@app.post('/api/companies/{company_id}/bank-statement/{line_id}/match')
def match_bank_statement(company_id: str, line_id: str, body: MatchInput, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    line = session.scalar(select(BankStatementLine).where(BankStatementLine.company_id == company_id, BankStatementLine.id == line_id))
    if not line: raise HTTPException(404, 'Statement line not found')
    if line.matched_record_id: raise HTTPException(409, 'Statement line is already matched')
    if session.scalar(select(BankMatchAllocation.id).where(BankMatchAllocation.company_id == company_id,
        BankMatchAllocation.statement_line_id == line.id)):
        raise HTTPException(409, 'Statement line has partial allocations; remove them first')
    record = bank_record_for_match(company_id, body.record_id, line, session)
    if record.kind=='bank_transfer' and record.data.get('direction')=='bank_to_bank':
        if line.amount!=bank_record_amount(record,line.bank_account_id):raise HTTPException(422,'Statement and transfer amounts differ')
        result=add_bank_match_allocation(company_id,line_id,BankMatchAllocationInput(record_id=record.id,amount=abs(line.amount)),user,session)
        return {'matched_record_id':record.id,'allocation_id':result['id']}
    if session.scalar(select(BankMatchAllocation.id).where(BankMatchAllocation.company_id == company_id,
        BankMatchAllocation.record_id == record.id)):
        raise HTTPException(409, 'Bank transaction has partial allocations; use allocation matching')
    expected=bank_record_amount(record,line.bank_account_id)
    if line.amount != expected: raise HTTPException(422, 'Statement and transaction amounts differ')
    line.matched_record_id = record.id
    audit(session, company_id, user, 'bank_statement.matched', 'bank_statement_line', line.id, {'record_id': record.id})
    try: session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Bank transaction is already matched')
    return {'matched_record_id': record.id}

@app.post('/api/companies/{company_id}/bank-statement/{line_id}/allocations', status_code=201)
def add_bank_match_allocation(company_id: str, line_id: str, body: BankMatchAllocationInput,
                              user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    line = session.scalar(select(BankStatementLine).where(BankStatementLine.company_id == company_id,
        BankStatementLine.id == line_id))
    if not line: raise HTTPException(404, 'Statement line not found')
    if line.matched_record_id: raise HTTPException(409, 'Legacy exact match must be removed first')
    record = bank_record_for_match(company_id, body.record_id, line, session)
    if session.scalar(select(BankStatementLine.id).where(BankStatementLine.company_id == company_id,
        BankStatementLine.matched_record_id == record.id,BankStatementLine.bank_account_id==line.bank_account_id)):
        raise HTTPException(409, 'Bank transaction already has an exact match')
    line_used = session.scalar(select(func.coalesce(func.sum(BankMatchAllocation.amount), 0)).where(
        BankMatchAllocation.company_id == company_id, BankMatchAllocation.statement_line_id == line.id))
    record_used = session.scalar(select(func.coalesce(func.sum(BankMatchAllocation.amount),0)).join(BankStatementLine,BankStatementLine.id==BankMatchAllocation.statement_line_id).where(BankMatchAllocation.company_id==company_id,BankMatchAllocation.record_id==record.id,BankStatementLine.bank_account_id==line.bank_account_id))
    if body.amount > abs(line.amount) - line_used or body.amount > record.amount - record_used:
        raise HTTPException(422, 'Allocation exceeds the remaining statement or bank transaction amount')
    allocation = BankMatchAllocation(company_id=company_id, statement_line_id=line.id,
                                     record_id=record.id, amount=body.amount)
    session.add(allocation)
    try:
        session.flush()
        audit(session, company_id, user, 'bank_statement.allocated', 'bank_match_allocation', allocation.id,
              {'line_id': line.id, 'record_id': record.id, 'amount': str(body.amount)})
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'This statement and bank transaction pair is already allocated')
    return {'id': allocation.id, 'statement_line_id': line.id, 'record_id': record.id, 'amount': str(allocation.amount)}

@app.delete('/api/companies/{company_id}/bank-statement/allocations/{allocation_id}')
def remove_bank_match_allocation(company_id: str, allocation_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    allocation = session.scalar(select(BankMatchAllocation).where(BankMatchAllocation.company_id == company_id,
        BankMatchAllocation.id == allocation_id))
    if not allocation: raise HTTPException(404, 'Match allocation not found')
    audit(session, company_id, user, 'bank_statement.allocation_removed', 'bank_match_allocation', allocation.id,
          {'line_id': allocation.statement_line_id, 'record_id': allocation.record_id, 'amount': str(allocation.amount)})
    session.delete(allocation); session.commit()
    return {'removed': allocation_id}

@app.delete('/api/companies/{company_id}/bank-statement/{line_id}/match')
def unmatch_bank_statement(company_id: str, line_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    line = session.scalar(select(BankStatementLine).where(BankStatementLine.company_id == company_id, BankStatementLine.id == line_id))
    if not line: raise HTTPException(404, 'Statement line not found')
    if not line.matched_record_id and session.scalar(select(BankMatchAllocation.id).where(
        BankMatchAllocation.company_id == company_id, BankMatchAllocation.statement_line_id == line.id)):
        raise HTTPException(409, 'Remove this line’s allocations individually')
    old_record_id = line.matched_record_id
    line.matched_record_id = None
    if old_record_id: audit(session, company_id, user, 'bank_statement.unmatched', 'bank_statement_line', line.id, {'record_id': old_record_id})
    session.commit()
    return {'matched_record_id': None}

@app.get('/api/companies/{company_id}/bank-reconciliation')
def bank_reconciliation(company_id: str, bank_account_id: str = 'default', as_of: DateType | None = None, opening_balance: Decimal = Query(Decimal('0')), user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if not opening_balance.is_finite() or abs(opening_balance) > Decimal('9999999999999.99') or opening_balance.as_tuple().exponent < -2:
        raise HTTPException(422, 'Opening balance must be a valid amount with at most two decimal places')
    bank_account = bank_account_for(company_id, bank_account_id, session)
    bank_id = bank_account.id if bank_account else None
    scope = BankStatementLine.bank_account_id == bank_id if bank_id else BankStatementLine.bank_account_id.is_(None)
    statement_query = select(BankStatementLine).where(BankStatementLine.company_id == company_id, scope)
    if as_of: statement_query = statement_query.where(BankStatementLine.date <= as_of)
    lines = list(session.scalars(statement_query))
    allocated = {}
    if lines:
        allocated = dict(session.execute(select(BankMatchAllocation.statement_line_id,
            func.sum(BankMatchAllocation.amount)).where(BankMatchAllocation.company_id == company_id,
            BankMatchAllocation.statement_line_id.in_([line.id for line in lines]))
            .group_by(BankMatchAllocation.statement_line_id)).all())
    bank = session.get(LedgerAccount, bank_account.ledger_account_id) if bank_account else session.scalar(select(LedgerAccount).where(LedgerAccount.company_id == company_id, LedgerAccount.code == SYSTEM_ACCOUNTS['bank'][0]))
    ledger_movement = Decimal('0')
    if bank:
        ledger_query = select(JournalLine.debit, JournalLine.credit).join(Journal, Journal.id == JournalLine.journal_id).where(JournalLine.company_id == company_id, JournalLine.account_id == bank.id, Journal.company_id == company_id)
        if as_of: ledger_query = ledger_query.where(Journal.date <= as_of)
        rows = session.execute(ledger_query)
        ledger_movement = sum((debit - credit for debit, credit in rows), Decimal('0'))
    statement_movement = sum((line.amount for line in lines), Decimal('0'))
    statement_closing = opening_balance + statement_movement
    matched = sum(bool(line.matched_record_id) or allocated.get(line.id, Decimal('0')) == abs(line.amount) for line in lines)
    return {'bank_account_id': bank_id or 'default', 'as_of': as_of.isoformat() if as_of else None, 'opening_balance': str(opening_balance), 'statement_movement': str(statement_movement), 'statement_closing_balance': str(statement_closing), 'ledger_movement': str(ledger_movement), 'ledger_closing_balance': str(ledger_movement), 'difference': str(statement_closing - ledger_movement), 'matched': matched, 'unmatched': len(lines) - matched}

def reconciliation_review_obj(review: BankReconciliationReview):
    return {'id': review.id, 'bank_account_id': review.bank_account_key, 'as_of': review.as_of.isoformat(),
            'opening_balance': str(review.opening_balance), 'statement_closing_balance': str(review.statement_closing_balance),
            'ledger_closing_balance': str(review.ledger_closing_balance), 'difference': str(review.difference),
            'matched': review.matched, 'unmatched': review.unmatched, 'note': review.note,
            'status': 'balanced' if review.difference == 0 and review.unmatched == 0 else 'needs_review',
            'created_at': review.created_at.isoformat()}

@app.get('/api/companies/{company_id}/bank-reconciliation/reviews')
def bank_reconciliation_reviews(company_id: str, bank_account_id: str = 'default', user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    bank_account_for(company_id, bank_account_id, session)
    reviews = session.scalars(select(BankReconciliationReview).where(
        BankReconciliationReview.company_id == company_id, BankReconciliationReview.bank_account_key == bank_account_id
    ).order_by(BankReconciliationReview.created_at.desc(), BankReconciliationReview.id.desc()).limit(100))
    return [reconciliation_review_obj(review) for review in reviews]

@app.post('/api/companies/{company_id}/bank-reconciliation/reviews', status_code=201)
def save_bank_reconciliation_review(company_id: str, body: ReconciliationReviewInput, user: User = Depends(current_user), session: Session = Depends(db)):
    lock_company(company_id, user, session)
    totals = bank_reconciliation(company_id, bank_account_id=body.bank_account_id, as_of=body.as_of,
                                 opening_balance=body.opening_balance, user=user, session=session)
    review = BankReconciliationReview(company_id=company_id, bank_account_key=body.bank_account_id,
        as_of=body.as_of, opening_balance=body.opening_balance,
        statement_closing_balance=Decimal(totals['statement_closing_balance']),
        ledger_closing_balance=Decimal(totals['ledger_closing_balance']), difference=Decimal(totals['difference']),
        matched=totals['matched'], unmatched=totals['unmatched'], note=body.note.strip(), created_by=user.id)
    session.add(review); session.flush()
    audit(session, company_id, user, 'bank_reconciliation.reviewed', 'bank_reconciliation_review', review.id,
          {'bank_account_id': body.bank_account_id, 'as_of': body.as_of.isoformat(), 'difference': totals['difference']})
    session.commit(); session.refresh(review)
    return reconciliation_review_obj(review)

@app.get('/api/companies/{company_id}/reports/summary')
def report_summary(company_id: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    if from_date > to_date: raise HTTPException(422, 'Start date must be before end date')
    postings = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    records = list(session.scalars(select(Record).where(Record.company_id == company_id, Record.id.in_(postings), Record.date >= from_date, Record.date <= to_date)))
    def total(kinds): return sum((r.amount for r in records if r.kind in kinds), Decimal('0'))
    sales = total({'sales_invoice', 'pos'}) - total({'credit_note'})
    purchases = total({'purchase_bill'}) - total({'debit_note'})
    expenses = total({'expense'})
    receipts = total({'payment_in','pos','supplier_refund'}) + sum((r.amount for r in records if r.kind=='advance_refund' and r.data.get('payment_kind')=='payment_out'),Decimal('0'))
    payments = total({'payment_out','expense','customer_refund'}) + sum((r.amount for r in records if r.kind=='advance_refund' and r.data.get('payment_kind')=='payment_in'),Decimal('0'))
    outstanding_rows = list(session.scalars(select(Record).where(Record.company_id == company_id, Record.id.in_(postings), Record.kind.in_(['sales_invoice', 'purchase_bill','opening_receivable','opening_payable']))))
    receivable = payable = Decimal('0')
    for r in outstanding_rows:
        remaining = r.amount - applied_total(company_id, r.id, session)
        if r.kind in {'sales_invoice','opening_receivable'}: receivable += remaining
        else: payable += remaining
    profile = session.get(CompanyTaxProfile, company_id)
    gst = None
    if not profile or profile.mode == 'regular':
        def tax_total(kinds, key): return sum((Decimal(str(r.data.get(key, 0))) for r in records if r.kind in kinds), Decimal('0'))
        def pending_total(kinds, key): return sum((Decimal(str(r.data.get('pending_input_' + key, r.data.get(key, 0)))) for r in records if r.kind in kinds), Decimal('0'))
        gst = {key: str(tax_total({'sales_invoice','pos','payment_in','advance_application','advance_refund'}, key) - tax_total({'credit_note'}, key)) for key in ('cgst', 'sgst', 'igst')}
        gst['input_pending_review'] = {key: str(pending_total({'purchase_bill','expense'}, key) - pending_total({'debit_note'}, key)) for key in ('cgst', 'sgst', 'igst')}
        gst['input_ineligible_in_cost'] = str(tax_total({'purchase_bill','expense'}, 'input_tax_ineligible') - tax_total({'debit_note'}, 'input_tax_ineligible'))
        def outward_value(kinds, field):
            return sum((Decimal(str(r.data.get(field, r.data.get('taxable', 0) if field == 'taxable_supply_value' else 0)))
                for r in records if r.kind in kinds), Decimal('0'))
        gst['outward_supply_values'] = {key: str(outward_value({'sales_invoice', 'pos'}, field) - outward_value({'credit_note'}, field))
            for key, field in (('taxable', 'taxable_supply_value'), ('nil_rated', 'nil_rated_value'), ('exempt', 'exempt_value'), ('non_gst', 'non_gst_value'))}
    return {'from_date': from_date.isoformat(), 'to_date': to_date.isoformat(), 'tax_mode': profile.mode if profile else 'regular', 'sales': str(sales), 'purchases': str(purchases), 'expenses': str(expenses), 'receipts': str(receipts), 'payments': str(payments), 'receivables': str(receivable), 'payables': str(payable), 'gst': gst, 'posted_records': len(records)}

@app.get('/api/companies/{company_id}/reports/summary.{fmt}')
def export_summary(company_id: str, fmt: str, from_date: DateType, to_date: DateType, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    data = report_summary(company_id, from_date, to_date, user, session)
    rows = [('Period', f"{data['from_date']} to {data['to_date']}")]
    rows += [(label, data[key]) for key, label in [('sales', 'Net sales'), ('purchases', 'Net purchases'), ('expenses', 'Expenses'), ('receipts', 'Payments received'), ('payments', 'Payments out'), ('receivables', 'Current receivables'), ('payables', 'Current payables')]]
    if data['gst']:
        rows += [('Output ' + key.upper(), data['gst'][key]) for key in ('cgst', 'sgst', 'igst')]
        rows += [('Input ' + key.upper() + ' pending review', data['gst']['input_pending_review'][key]) for key in ('cgst', 'sgst', 'igst')]
        rows.append(('Supplier GST included in cost', data['gst']['input_ineligible_in_cost']))
        rows += [(label, data['gst']['outward_supply_values'][key]) for key, label in (('taxable', 'Taxable outward value'), ('nil_rated', 'Nil-rated outward value'), ('exempt', 'Exempt outward value'), ('non_gst', 'Non-GST outward value'))]
    return export_table(company.name, 'Posted transaction summary', ['Metric', 'Value'], rows, fmt, f'summary.{fmt}')

@app.get('/api/companies/{company_id}/documents/{record_id}.pdf')
def document_pdf(company_id: str, record_id: str, template: str = '', user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    record = session.scalar(select(Record).where(Record.company_id == company_id, Record.id == record_id, Record.kind.in_(DOCUMENTS|{'payment_in','payment_out','customer_refund','supplier_refund','advance_refund'})))
    if not record: raise HTTPException(404, 'Document not found')
    from types import SimpleNamespace
    current_brand=branding_for(company_id,session);document_data=dict(record.data)
    if record.kind in {'sales_invoice', 'purchase_bill'}:
        # Settlement also includes credit/debit notes. Show actual payments separately.
        payments = Decimal('0')
        for allocation in (PaymentAllocation, PaymentSplitAllocation):
            query = select(func.coalesce(func.sum(allocation.amount), 0)).join(Record, Record.id == allocation.payment_id).where(
                allocation.company_id == company_id, allocation.document_id == record.id,
                Record.company_id == company_id, Record.kind.in_(['payment_in', 'payment_out', 'advance_application']))
            payments += Decimal(str(session.scalar(query)))
        document_data['payments_applied'] = str(payments)
    if 'logo' in current_brand:document_data['document_branding']={**(document_data.get('document_branding') or {}),'logo':current_brand['logo']}
    record=SimpleNamespace(id=record.id,kind=record.kind,name=record.name,number=record.number,date=record.date,amount=record.amount,data=document_data)
    voucher=record.kind in {'payment_in','payment_out','customer_refund','supplier_refund','advance_refund'}
    if voucher:
        from types import SimpleNamespace
        data=dict(record.data);taxed=bool(data.get('advance_tax_event'))
        if taxed:
            data={**data,**{key:str(abs(Decimal(str(data.get(key,0))))) for key in ('cgst','sgst','igst','taxable','taxable_supply_value')}}
            if not data.get('taxable') or Decimal(data['taxable'])==0:data['taxable']=str(record.amount-sum(Decimal(data[key]) for key in ('cgst','sgst','igst')))
            data['lines']=[{**line,**{key:str(abs(Decimal(str(line.get(key,0))))) for key in ('rate','taxable','tax')}} for line in data.get('lines',[])]
        else:
            data.update(tax_mode='unregistered',taxable=str(record.amount),cgst='0',sgst='0',igst='0',lines=[{'description':record.kind.replace('_',' ').title(),'quantity':'1','rate':str(record.amount),'taxable':str(record.amount),'tax':'0','gst_rate':'0'}])
        links=list(session.scalars(select(PaymentAllocation).where(PaymentAllocation.company_id==company_id,PaymentAllocation.payment_id==record.id)))+list(session.scalars(select(PaymentSplitAllocation).where(PaymentSplitAllocation.company_id==company_id,PaymentSplitAllocation.payment_id==record.id)))
        references=[]
        for link in links:
            target=session.scalar(select(Record).where(Record.company_id==company_id,Record.id==link.document_id))
            if target:references.append((target.number or target.name)+' · INR '+str(link.amount))
        if references:data['notes']=(str(data.get('notes',''))+chr(10)+'Applied to: '+', '.join(references)).strip()
        if data.get('is_advance'):data['notes']=(str(data.get('notes',''))+chr(10)+'Advance payment; unused amounts remain available for application or refund.').strip()
        record=SimpleNamespace(id=record.id,kind=record.kind,name=record.name,number=record.number,date=record.date,amount=record.amount,data=data)

    palette = {
        'classic': (colors.HexColor('#244f43'), colors.HexColor('#edf4ee'), 8, True),
        'modern': (colors.HexColor('#1a6475'), colors.HexColor('#e7f2f5'), 12, False),
        'compact': (colors.HexColor('#343c45'), colors.HexColor('#f3f4f5'), 5, True),
        'bold': (colors.HexColor('#752f39'), colors.HexColor('#f8ecee'), 13, True),
        'minimal': (colors.HexColor('#343c45'), colors.white, 10, False),
    }
    if not template:
        preference = session.get(CompanyPreference, company_id)
        template = preference.document_template if preference else 'classic'
    from document_layouts import LAYOUTS, render_document
    if template in LAYOUTS:
        data = record.data or {}
        supplier = data.get('company_snapshot') or company_obj(session.get(Company, company_id), session)
        mode = data.get('tax_mode', supplier.get('tax_mode', 'regular'))
        bill = mode == 'composition' or mode == 'regular' and data.get('document_tax_form') == 'bill_of_supply'
        title = {'sales_invoice': 'Bill of Supply' if bill else 'Invoice-cum-Bill of Supply' if data.get('document_tax_form') == 'invoice_cum_bill' else 'Tax Invoice' if mode == 'regular' else 'Invoice', 'purchase_bill': 'Purchase Bill', 'estimate': 'Quotation', 'proforma': 'Proforma Invoice', 'sales_order': 'Sales Order', 'credit_note': 'Credit Note', 'debit_note': 'Debit Note', 'purchase_order': 'Purchase Order', 'expense':'Expense Voucher','payment_in':'Receipt Voucher','payment_out':'Payment Voucher','customer_refund':'Customer Refund Voucher','supplier_refund':'Supplier Refund Receipt','advance_refund':'Advance Refund Voucher', 'pos': 'Bill of Supply Receipt' if bill else 'POS Receipt'}[record.kind]
        paid = applied_total(company_id, record.id, session) if record.kind in {'sales_invoice', 'purchase_bill'} else record.amount if record.kind == 'pos' or voucher else Decimal('0')
        paid = record.amount - available_credit(sys.modules[__name__],company_id,record,session) if record.kind in {'credit_note','debit_note'} else record.amount if record.kind=='expense' else paid
        branding={**(data.get('document_branding') or {}),**{k:data[k] for k in ('notes','terms') if data.get(k)}}
        if voucher:
            branding={**branding,'upi_id':''}
            bank=bank_account_for(company_id,str(data.get('bank_account_id') or 'default'),session) if data.get('payment_account')=='bank' else None
            if bank:branding.update(bank_name=bank.name,account_number=bank.account_hint,ifsc='',branch='')
            elif data.get('payment_account','cash')=='cash':branding.update(bank_name='',account_number='',ifsc='',branch='')
        result = render_document(record, supplier, branding, template, title, paid)
        return Response(result, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{record.kind}-{record.id[:8]}.pdf"'})
    if template not in palette: raise HTTPException(404, 'Document layout not found')
    accent, tint, padding, grid = palette[template]
    data = record.data or {}
    supplier = data.get('company_snapshot') or company_obj(session.get(Company, company_id), session)
    tax_mode = data.get('tax_mode', supplier.get('tax_mode', 'regular'))
    def safe(value):
        from html import escape
        return escape(str(value or ''))
    bill_of_supply = tax_mode == 'composition' or tax_mode == 'regular' and data.get('document_tax_form') == 'bill_of_supply'
    title = {'sales_invoice': 'Bill of Supply' if bill_of_supply else 'Invoice-cum-Bill of Supply' if data.get('document_tax_form') == 'invoice_cum_bill' else 'Tax Invoice' if tax_mode == 'regular' else 'Invoice', 'purchase_bill': 'Purchase Bill', 'estimate': 'Estimate', 'proforma': 'Proforma Invoice', 'sales_order': 'Sales Order', 'credit_note': 'Credit Note', 'debit_note': 'Debit Note', 'purchase_order': 'Purchase Order', 'expense':'Expense Voucher','payment_in':'Receipt Voucher','payment_out':'Payment Voucher','customer_refund':'Customer Refund Voucher','supplier_refund':'Supplier Refund Receipt','advance_refund':'Advance Refund Voucher', 'pos': 'Bill of Supply Receipt' if bill_of_supply else 'POS Receipt'}[record.kind]
    out = io.BytesIO()
    pdf = SimpleDocTemplate(out, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40, title=title)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ApexTitle', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=20 if template != 'compact' else 15, leading=23, textColor=accent, spaceAfter=10))
    styles.add(ParagraphStyle(name='ApexBody', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=13))
    styles.add(ParagraphStyle(name='ApexHead', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, leading=13, textColor=colors.white))
    styles.add(ParagraphStyle(name='ApexSmall', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#52605b')))
    styles.add(ParagraphStyle(name='ApexRight', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, alignment=TA_RIGHT, textColor=accent))
    elements = [Paragraph(safe(title), styles['ApexTitle'])]
    legacy_branding=data.get('document_branding') or {}
    if legacy_branding.get('logo'):
        from reportlab.platypus import Image as PdfImage
        logo=PdfImage(io.BytesIO(base64.b64decode(legacy_branding['logo'].split(',',1)[1])));logo._restrictSize(95,60);elements.insert(0,logo)
    if tax_mode == 'composition' and record.kind in {'sales_invoice', 'pos'}:
        elements.append(Paragraph('Composition taxable person, not eligible to collect tax on supplies', styles['ApexBody']))
    header = Table([
        [Paragraph('<b>' + safe(supplier.get('name')) + '</b><br/>' + safe(supplier.get('address')) + ('<br/>GSTIN: ' + safe(supplier.get('gstin')) if supplier.get('gstin') else ''), styles['ApexBody']),
         Paragraph('<b>No:</b> ' + safe(record.number or record.id[:8]) + '<br/><b>Date:</b> ' + record.date.isoformat() + ('<br/><b>Due date:</b> ' + safe(data['due_date']) if data.get('due_date') else '') + ('<br/><b>Place of supply:</b> ' + safe(data.get('place_of_supply')) if tax_mode == 'regular' else ''), styles['ApexBody'])],
        [Paragraph('<b>Bill to</b><br/>' + safe(record.name) + '<br/>' + safe(data.get('party_address')) + ('<br/>GSTIN: ' + safe(data.get('party_gstin')) if data.get('party_gstin') else ''), styles['ApexBody']), '']
    ], colWidths=[280, 235])
    header.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), tint), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), padding), ('TOPPADDING', (0, 0), (-1, -1), padding), ('BOTTOMPADDING', (0, 0), (-1, -1), padding)]))
    elements += [header, Spacer(1, 18)]
    has_gst = (tax_mode == 'regular' and not (bill_of_supply and record.kind in {'sales_invoice', 'pos'})) or any(Decimal(str(line.get('tax', 0))) > 0 for line in data.get('lines', []))
    headings = ['Description', 'HSN / SAC', 'Qty', 'Rate', 'Disc.', 'GST', 'Amount'] if has_gst else ['Description', 'HSN / SAC', 'Qty', 'Rate', 'Disc.', 'Amount']
    widths = [155, 55, 35, 60, 42, 65, 103] if has_gst else [190, 65, 45, 70, 50, 95]
    rows = [[Paragraph(safe(h), styles['ApexHead']) for h in headings]]
    for line in data.get('lines', []):
        description = safe(line.get('description'))
        if line.get('tax_treatment') in {'nil_rated', 'exempt', 'non_gst'}:
            description += '<br/><font size="7" color="#52605b">' + {'nil_rated': 'Nil-rated supply', 'exempt': 'Exempt supply', 'non_gst': 'Non-GST supply'}[line['tax_treatment']] + '</font>'
        if tax_mode == 'regular' and record.kind in {'purchase_bill', 'purchase_order', 'debit_note'} and Decimal(str(line.get('tax', 0))) > 0:
            treatment = 'GST included in cost' if line.get('itc_treatment') == 'ineligible' else 'Input credit pending review'
            description += '<br/><font size="7" color="#52605b">' + treatment + '</font>'
        base = [Paragraph(description, styles['ApexBody']), safe(line.get('hsn')), safe(line.get('quantity')), safe(line.get('rate')), safe(line.get('discount_percent', '0')) + '%']
        if has_gst: base.append(safe(line.get('gst_rate')) + '%')
        base.append(safe(Decimal(str(line.get('taxable', 0))) + Decimal(str(line.get('tax', 0)))))
        rows.append(base)
    if len(rows) == 1: rows.append([safe(record.name)] + [''] * (len(headings) - 2) + [safe(record.amount)])
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
    table_style = [('BACKGROUND', (0, 0), (-1, 0), accent), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), padding), ('BOTTOMPADDING', (0, 0), (-1, -1), padding)]
    if grid: table_style.append(('LINEBELOW', (0, 0), (-1, -1), .3, colors.HexColor('#dce4df')))
    table.setStyle(TableStyle(table_style)); elements += [table, Spacer(1, 18)]
    total_discount = sum((Decimal(str(line.get('discount', 0))) for line in data.get('lines', [])), Decimal('0'))
    totals = []
    if total_discount > 0:
        totals += [('Gross value', money(Decimal(str(data.get('taxable', 0))) + total_discount)), ('Discount', total_discount)]
    totals += [('Subtotal', data.get('taxable', record.amount))]
    if has_gst:
        totals += [(key.upper(), data.get(key, '0.00')) for key in ('cgst', 'sgst', 'igst') if Decimal(str(data.get(key, 0))) > 0]
        if Decimal(str(data.get('supplier_tax', 0))) > 0: totals.append(('Supplier tax (unclassified)', data['supplier_tax']))
    if record.kind == 'pos': totals.append(('Paid through', str(data.get('payment_account', 'cash')).title()))
    if Decimal(str(data.get('additional_charges', 0))): totals.append(('Additional charges', data['additional_charges']))
    if Decimal(str(data.get('round_off', 0))): totals.append(('Round off', data['round_off']))
    totals.append(('Total (INR)', record.amount))
    total_table = Table([[Paragraph(safe(label), styles['ApexSmall']), Paragraph(safe(value), styles['ApexRight'])] for label, value in totals], colWidths=[385, 130], hAlign='RIGHT')
    total_table.setStyle(TableStyle([('LINEABOVE', (0, -1), (-1, -1), 1, accent), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    elements += [total_table, Spacer(1, 20), Paragraph('Generated from Apex Books. Verify particulars and signature requirements before issue.', styles['ApexSmall'])]
    pdf.build(elements)
    return Response(out.getvalue(), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{record.kind}-{record.number or record.id[:8]}.pdf"'})
@app.get('/api/companies/{company_id}/export.{fmt}')
def export(company_id: str, fmt: str, kind: str = '', user: User = Depends(current_user), session: Session = Depends(db)):
    c = company_for(company_id, user, session)
    q = select(Record).where(Record.company_id == company_id)
    if kind: q = q.where(Record.kind == kind)
    rows = list(session.scalars(q.order_by(Record.date.desc())))
    out = io.BytesIO()
    if fmt == 'xlsx':
        book = Workbook(); sheet = book.active; sheet.title = 'Register'; sheet.append(['Date', 'Type', 'Number', 'Party / name', 'Amount (INR)'])
        for r in rows: sheet.append([r.date.isoformat(), r.kind, r.number, r.name, float(r.amount)])
        book.save(out); media = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif fmt == 'pdf':
        pdf = canvas.Canvas(out, pagesize=A4); pdf.setTitle('Apex Books register'); pdf.drawString(40, 800, f'{c.name} — Transaction register'); y = 770
        for r in rows:
            if y < 45: pdf.showPage(); y = 800
            pdf.drawString(40, y, f'{r.date}  {r.kind}  {r.number}  {r.name}'[:85]); pdf.drawRightString(555, y, str(r.amount)); y -= 20
        pdf.save(); media = 'application/pdf'
    else: raise HTTPException(404, 'Unsupported export format')
    return Response(out.getvalue(), media_type=media, headers={'Content-Disposition': f'attachment; filename="register.{fmt}"'})

@app.get('/api/companies/{company_id}/data-export.json')
def company_data_export(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    company = company_for(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can export all company data')
    accounts = list(session.scalars(select(LedgerAccount).where(LedgerAccount.company_id == company_id)))
    journals = list(session.scalars(select(Journal).where(Journal.company_id == company_id)))
    lines = list(session.scalars(select(JournalLine).where(JournalLine.company_id == company_id)))
    records = list(session.scalars(select(Record).where(Record.company_id == company_id)))
    postings = list(session.scalars(select(RecordPosting).where(RecordPosting.company_id == company_id)))
    conversions = list(session.scalars(select(DocumentConversion).where(DocumentConversion.company_id == company_id)))
    allocations = list(session.scalars(select(PaymentAllocation).where(PaymentAllocation.company_id == company_id)))
    allocations += list(session.scalars(select(PaymentSplitAllocation).where(PaymentSplitAllocation.company_id == company_id)))
    bank_accounts = list(session.scalars(select(BankAccount).where(BankAccount.company_id == company_id)))
    statement = list(session.scalars(select(BankStatementLine).where(BankStatementLine.company_id == company_id)))
    bank_match_allocations = list(session.scalars(select(BankMatchAllocation).where(BankMatchAllocation.company_id == company_id)))
    reconciliation_reviews = list(session.scalars(select(BankReconciliationReview).where(BankReconciliationReview.company_id == company_id)))
    stock_movements = list(session.scalars(select(StockMovement).where(StockMovement.company_id == company_id)))
    events = list(session.scalars(select(AuditEvent).where(AuditEvent.company_id == company_id)))
    series = list(session.scalars(select(NumberSeries).where(NumberSeries.company_id == company_id)))
    members = list(session.scalars(select(CompanyMember).where(CompanyMember.company_id == company_id)))
    period_lock = session.get(PeriodLock, company_id)
    payload = {'schema_version': 7, 'exported_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'single_company_data_export', 'company': company_obj(company, session, user),
        'preferences': get_preferences(company_id, user, session),
        'members': [{'email': session.get(User, m.user_id).email, 'role': m.role} for m in members],
        'records': [{**obj(r), 'company_id': company_id} for r in records],
        'accounts': [{'id': a.id, 'code': a.code, 'name': a.name, 'category': a.category} for a in accounts],
        'journals': [{'id': j.id, 'date': j.date.isoformat(), 'reference': j.reference, 'memo': j.memo} for j in journals],
        'journal_lines': [{'journal_id': l.journal_id, 'account_id': l.account_id, 'debit': str(l.debit), 'credit': str(l.credit)} for l in lines],
        'journal_reversals': [{'original_id': r.original_id, 'reversal_id': r.reversal_id} for r in session.scalars(select(JournalReversal).where(JournalReversal.company_id == company_id))],
        'record_postings': [{'record_id': p.record_id, 'journal_id': p.journal_id} for p in postings],
        'document_conversions': [{'source_record_id': c.source_record_id, 'target_record_id': c.target_record_id} for c in conversions],
        'payment_allocations': [{'payment_id': a.payment_id, 'document_id': a.document_id, 'amount': str(a.amount)} for a in allocations],
        'bank_accounts': [{'id': b.id, 'ledger_account_id': b.ledger_account_id, 'name': b.name, 'account_hint': b.account_hint} for b in bank_accounts],
        'bank_statement_lines': [{'id': l.id, 'bank_account_id': l.bank_account_id or 'default', 'date': l.date.isoformat(), 'description': l.description, 'reference': l.reference, 'amount': str(l.amount), 'matched_record_id': l.matched_record_id} for l in statement],
        'bank_match_allocations': [{'id': a.id, 'statement_line_id': a.statement_line_id, 'record_id': a.record_id, 'amount': str(a.amount)} for a in bank_match_allocations],
        'bank_reconciliation_reviews': [reconciliation_review_obj(review) for review in reconciliation_reviews],
        'stock_movements': [{'id': movement.id, 'item_id': movement.item_id, 'source_record_id': movement.source_record_id,
            'line_index': movement.line_index, 'date': movement.date.isoformat(), 'quantity': str(movement.quantity),
            'cost_value': str(movement.cost_value) if movement.cost_value is not None else None} for movement in stock_movements],
        'audit_events': [{'id': e.id, 'actor': session.get(User, e.actor_id).email, 'occurred_at': e.occurred_at.isoformat(), 'action': e.action, 'entity_type': e.entity_type, 'entity_id': e.entity_id, 'details': e.details} for e in events],
        'number_series': [{'kind': s.kind, 'financial_year': s.financial_year, 'prefix': s.prefix, 'next_number': s.next_number} for s in series],
        'locked_through': period_lock.locked_through.isoformat() if period_lock else None}
    from company_restore import pack
    return Response(json.dumps(pack(payload), allow_nan=False), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="company-data.json"'})


from workflow_extensions import install as install_workflows
install_workflows(app, sys.modules[__name__])

from company_restore import install as install_company_restore
install_company_restore(app, sys.modules[__name__])

from auth_workflows import install as install_auth_workflows
install_auth_workflows(app, sys.modules[__name__])

from document_edits import install as install_document_edits
install_document_edits(app, sys.modules[__name__])

from gst_returns import install as install_gst_returns
install_gst_returns(app, sys.modules[__name__])

from party_statements import install as install_party_statements
install_party_statements(app, sys.modules[__name__])

from commerce import install as install_commerce
install_commerce(app, sys.modules[__name__])

from everyday_features import install as install_everyday_features
install_everyday_features(app, sys.modules[__name__])
