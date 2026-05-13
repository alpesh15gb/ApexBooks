"""add production hardening tables

Revision ID: 0003_production_hardening
Revises: 0002_normalized_accounting
Create Date: 2026-05-14
"""
from alembic import op
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey,
    UniqueConstraint, Index, Numeric
)
from datetime import datetime

revision = '0003_production_hardening'
down_revision = '0002_normalized_accounting'
branch_labels = None
depends_on = None

def upgrade():
    # Period Locks
    op.create_table(
        'period_locks',
        Column('id', Integer, primary_key=True, autoincrement=True),
        Column('tenant_id', String(64), index=True, nullable=False),
        Column('lock_year', Integer, nullable=False),
        Column('lock_month', Integer, nullable=False),
        Column('is_locked', Boolean, default=False),
        Column('locked_by', String(64)),
        Column('locked_at', DateTime),
        Column('created_at', DateTime, default=datetime.utcnow),
        UniqueConstraint('tenant_id', 'lock_year', 'lock_month', name='uq_period_lock'),
    )

    # Idempotency Keys
    op.create_table(
        'idempotency_keys',
        Column('id', Integer, primary_key=True, autoincrement=True),
        Column('tenant_id', String(64), index=True, nullable=False),
        Column('idempotency_key', String(128), nullable=False),
        Column('response', Text, default='{}'),
        Column('created_at', DateTime, default=datetime.utcnow),
        UniqueConstraint('tenant_id', 'idempotency_key', name='uq_idempotency'),
    )

    # Additional indexes for performance
    op.create_index('ix_gl_tenant_date', 'gl_entries', ['tenant_id', 'posting_date'])
    op.create_index('ix_gl_account_date', 'gl_entries', ['account', 'posting_date'])
    op.create_index('ix_invoices_tenant_date', 'invoices', ['tenant_id', 'invoice_date'])
    op.create_index('ix_invoices_party_date', 'invoices', ['tenant_id', 'party_id', 'invoice_date'])
    op.create_index('ix_invoices_status_date', 'invoices', ['status', 'invoice_date'])
    op.create_index('ix_invoices_paid_status', 'invoices', ['tenant_id', 'payment_status'])

def downgrade():
    op.drop_index('ix_invoices_paid_status', table_name='invoices')
    op.drop_index('ix_invoices_status_date', table_name='invoices')
    op.drop_index('ix_invoices_party_date', table_name='invoices')
    op.drop_index('ix_invoices_tenant_date', table_name='invoices')
    op.drop_index('ix_gl_account_date', table_name='gl_entries')
    op.drop_index('ix_gl_tenant_date', table_name='gl_entries')
    op.drop_table('idempotency_keys')
    op.drop_table('period_locks')