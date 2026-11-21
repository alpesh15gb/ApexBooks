import os
from auth_config import require_jwt_secret
from business_calendar import business_today
from datetime import date as DateType, datetime, timezone
from decimal import Decimal
from fastapi.security import HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, JSON, Numeric, String,
    UniqueConstraint, create_engine, event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from uuid import uuid4


DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./apex.db')


if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+psycopg://', 1)
elif DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)


SECRET = require_jwt_secret()


engine = create_engine(DATABASE_URL, pool_pre_ping=True, hide_parameters=True, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {})


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
    book_label: Mapped[str] = mapped_column(String(80), nullable=False, default='', server_default='')
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
    date: Mapped[DateType] = mapped_column(Date, default=business_today)
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


class MasterImportReceipt(Base):
    __tablename__ = 'master_import_receipts'
    __table_args__ = (UniqueConstraint('company_id', 'operation_key'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(80), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class BankImportReceipt(Base):
    __tablename__ = 'bank_import_receipts'
    __table_args__ = (UniqueConstraint('company_id', 'operation_key'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(80), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


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
