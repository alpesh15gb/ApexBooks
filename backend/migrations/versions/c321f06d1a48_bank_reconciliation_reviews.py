"""Persist dated bank reconciliation reviews.

Revision ID: c321f06d1a48
Revises: a6d6f192e59b
"""
from alembic import op
import sqlalchemy as sa

revision = 'c321f06d1a48'
down_revision = 'a6d6f192e59b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('bank_reconciliation_reviews',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('company_id', sa.String(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('bank_account_key', sa.String(), nullable=False),
        sa.Column('as_of', sa.Date(), nullable=False),
        sa.Column('opening_balance', sa.Numeric(15, 2), nullable=False),
        sa.Column('statement_closing_balance', sa.Numeric(15, 2), nullable=False),
        sa.Column('ledger_closing_balance', sa.Numeric(15, 2), nullable=False),
        sa.Column('difference', sa.Numeric(15, 2), nullable=False),
        sa.Column('matched', sa.Integer(), nullable=False),
        sa.Column('unmatched', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(500), nullable=False),
        sa.Column('created_by', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_bank_reconciliation_reviews_company_id', 'bank_reconciliation_reviews', ['company_id'])
    op.create_index('ix_bank_reconciliation_reviews_bank_account_key', 'bank_reconciliation_reviews', ['bank_account_key'])


def downgrade():
    raise RuntimeError('Reconciliation history must be preserved; restore a verified backup instead.')
