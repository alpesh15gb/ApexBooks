from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class PartyModel(Base):
    __tablename__ = 'parties'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'party_id', name='uq_parties_tenant_party_id'),
        Index('ix_parties_tenant_name', 'tenant_id', 'party_name'),
        Index('ix_parties_tenant_gstin', 'tenant_id', 'gstin'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    party_id: Mapped[str] = mapped_column(String(64), nullable=False)
    party_type: Mapped[str] = mapped_column(String(20), nullable=False)
    party_name: Mapped[str] = mapped_column(String(255), nullable=False)
    gstin: Mapped[str | None] = mapped_column(String(15))
    pan: Mapped[str | None] = mapped_column(String(10))
    party_category: Mapped[str | None] = mapped_column(String(50))
    registration_type: Mapped[str | None] = mapped_column(String(50))
    state_code: Mapped[str | None] = mapped_column(String(2), index=True)
    credit_limit: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    credit_days: Mapped[int] = mapped_column(Integer, default=0)
    opening_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    tds_applicable: Mapped[bool] = mapped_column(Boolean, default=False)
    addresses: Mapped[list] = mapped_column(JSON, default=list)
    contacts: Mapped[list] = mapped_column(JSON, default=list)
    bank_accounts: Mapped[list] = mapped_column(JSON, default=list)
    custom_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ItemModel(Base):
    __tablename__ = 'items'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'item_id', name='uq_items_tenant_item_id'),
        UniqueConstraint('tenant_id', 'item_code', name='uq_items_tenant_item_code'),
        Index('ix_items_tenant_hsn', 'tenant_id', 'hsn_code'),
        Index('ix_items_tenant_sac', 'tenant_id', 'sac_code'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    item_code: Mapped[str] = mapped_column(String(64), nullable=False)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    hsn_code: Mapped[str | None] = mapped_column(String(8), index=True)
    sac_code: Mapped[str | None] = mapped_column(String(6), index=True)
    unit_of_measure: Mapped[str] = mapped_column(String(32), default='Nos')
    gst_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    cess_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    selling_price: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    purchase_price: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    stock_keeping_unit: Mapped[bool] = mapped_column(Boolean, default=False)
    custom_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class InvoiceModel(Base):
    __tablename__ = 'invoices'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'invoice_id', name='uq_invoices_tenant_invoice_id'),
        UniqueConstraint('tenant_id', 'invoice_number', name='uq_invoices_tenant_invoice_number'),
        Index('ix_invoices_tenant_type_date', 'tenant_id', 'invoice_kind', 'invoice_date'),
        Index('ix_invoices_tenant_party', 'tenant_id', 'party_id'),
        Index('ix_invoices_tenant_status', 'tenant_id', 'status'),
        Index('ix_invoices_tenant_date', 'tenant_id', 'invoice_date'),
        Index('ix_invoices_party_date', 'tenant_id', 'party_id', 'invoice_date'),
        Index('ix_invoices_status_date', 'status', 'invoice_date'),
        Index('ix_invoices_paid_status', 'tenant_id', 'payment_status'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    invoice_id: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_type: Mapped[str] = mapped_column(String(50), default='Regular')
    invoice_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    party_id: Mapped[str | None] = mapped_column(String(64), index=True)
    party_gstin: Mapped[str | None] = mapped_column(String(15), index=True)
    place_of_supply: Mapped[str] = mapped_column(String(2), index=True)
    supply_type: Mapped[str] = mapped_column(String(50), default='B2B')
    reverse_charge: Mapped[bool] = mapped_column(Boolean, default=False)
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    total_discount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    total_cgst: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    total_sgst: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    total_igst: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    total_cess: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    round_off: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    grand_total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    amount_paid: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    outstanding_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[str] = mapped_column(String(30), default='Draft', index=True)
    payment_status: Mapped[str] = mapped_column(String(30), default='Unpaid')
    irn: Mapped[str | None] = mapped_column(String(128), index=True)
    e_invoice_status: Mapped[str | None] = mapped_column(String(30))
    eway_bill_no: Mapped[str | None] = mapped_column(String(64))
    billing_address: Mapped[dict] = mapped_column(JSON, default=dict)
    shipping_address: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    custom_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    lines: Mapped[list['InvoiceLineModel']] = relationship('InvoiceLineModel', cascade='all, delete-orphan', back_populates='invoice')

    def __init__(self, **kwargs):
        if 'invoice_date' in kwargs and isinstance(kwargs['invoice_date'], str):
            kwargs['invoice_date'] = date.fromisoformat(kwargs['invoice_date'][:10])
        if 'due_date' in kwargs and kwargs.get('due_date') and isinstance(kwargs['due_date'], str):
            kwargs['due_date'] = date.fromisoformat(kwargs['due_date'][:10])
        super().__init__(**kwargs)


class InvoiceLineModel(Base):
    __tablename__ = 'invoice_lines'
    __table_args__ = (
        Index('ix_invoice_lines_tenant_item', 'tenant_id', 'item_id'),
        Index('ix_invoice_lines_tenant_hsn', 'tenant_id', 'hsn_code'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    invoice_pk: Mapped[int] = mapped_column(ForeignKey('invoices.id'), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[str | None] = mapped_column(String(64), index=True)
    item_code: Mapped[str | None] = mapped_column(String(64))
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hsn_code: Mapped[str | None] = mapped_column(String(8), index=True)
    sac_code: Mapped[str | None] = mapped_column(String(6), index=True)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    unit: Mapped[str] = mapped_column(String(32), default='Nos')
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    taxable_value: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    gst_rate: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    cgst_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    sgst_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    igst_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    cess_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    invoice: Mapped[InvoiceModel] = relationship('InvoiceModel', back_populates='lines')


class PaymentModel(Base):
    __tablename__ = 'payments'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'payment_id', name='uq_payments_tenant_payment_id'),
        Index('ix_payments_tenant_party', 'tenant_id', 'party_id'),
        Index('ix_payments_tenant_date', 'tenant_id', 'payment_date'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    payment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_mode: Mapped[str | None] = mapped_column(String(30))
    payment_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    party_id: Mapped[str | None] = mapped_column(String(64), index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    tds_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    net_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    reference_no: Mapped[str | None] = mapped_column(String(128), index=True)
    narration: Mapped[str | None] = mapped_column(Text)
    allocations: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default='Draft', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __init__(self, **kwargs):
        if 'payment_date' in kwargs and isinstance(kwargs['payment_date'], str):
            kwargs['payment_date'] = date.fromisoformat(kwargs['payment_date'][:10])
        super().__init__(**kwargs)


class GLEntryModel(Base):
    __tablename__ = 'gl_entries'
    __table_args__ = (
        Index('ix_gl_tenant_account_date', 'tenant_id', 'account', 'posting_date'),
        Index('ix_gl_tenant_party', 'tenant_id', 'party_id'),
        Index('ix_gl_tenant_voucher', 'tenant_id', 'voucher_type', 'voucher_id'),
        Index('ix_gl_tenant_date', 'tenant_id', 'posting_date'),
        Index('ix_gl_account_date', 'account', 'posting_date'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    posting_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    account: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    party_id: Mapped[str | None] = mapped_column(String(64), index=True)
    voucher_type: Mapped[str] = mapped_column(String(64), nullable=False)
    voucher_id: Mapped[str] = mapped_column(String(64), nullable=False)
    debit: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    credit: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        if 'posting_date' in kwargs and isinstance(kwargs['posting_date'], str):
            kwargs['posting_date'] = date.fromisoformat(kwargs['posting_date'][:10])
        super().__init__(**kwargs)


class GSTReturnModel(Base):
    __tablename__ = 'gst_returns'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'return_type', 'period_month', 'period_year', name='uq_gst_return_period'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    return_type: Mapped[str] = mapped_column(String(20), nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default='Draft')
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    arn: Mapped[str | None] = mapped_column(String(128))
    filed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PeriodLockModel(Base):
    __tablename__ = 'period_locks'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'lock_year', 'lock_month', name='uq_period_lock'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    lock_year: Mapped[int] = mapped_column(Integer, nullable=False)
    lock_month: Mapped[int] = mapped_column(Integer, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_by: Mapped[str | None] = mapped_column(String(64))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IdempotencyKeyModel(Base):
    __tablename__ = 'idempotency_keys'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'idempotency_key', name='uq_idempotency'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)