"""Add Account and JournalEntry models

Revision ID: 0005
Revises: 0004_tenant_settings
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004_tenant_settings'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('accounts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('code', sa.String(32), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('account_type', sa.String(50), server_default='Expense', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_accounts_tenant_code')
    )
    op.create_index('ix_accounts_tenant_type', 'accounts', ['tenant_id', 'account_type'])

    op.create_table('journal_entries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(64), nullable=False),
        sa.Column('entry_date', sa.Date(), nullable=False),
        sa.Column('reference', sa.String(64), nullable=True),
        sa.Column('narration', sa.Text(), nullable=True),
        sa.Column('entries', sa.JSON(), server_default='[]', nullable=False),
        sa.Column('total_debit', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
        sa.Column('total_credit', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_journal_entries_tenant_date', 'journal_entries', ['tenant_id', 'entry_date'])