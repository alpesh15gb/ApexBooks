"""Store split payment allocations alongside existing single allocations.

Revision ID: b3486c812f14
Revises: a70e29b0f6bc
"""
from alembic import op
import sqlalchemy as sa

revision = 'b3486c812f14'
down_revision = 'a70e29b0f6bc'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('payment_split_allocations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('company_id', sa.String(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('payment_id', sa.String(), sa.ForeignKey('records.id'), nullable=False),
        sa.Column('document_id', sa.String(), sa.ForeignKey('records.id'), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.UniqueConstraint('company_id', 'payment_id', 'document_id', name='uq_payment_split_document'),
        sa.CheckConstraint('amount > 0', name='payment_split_amount_positive'))
    for column in ('company_id', 'payment_id', 'document_id'):
        op.create_index('ix_payment_split_allocations_' + column, 'payment_split_allocations', [column])


def downgrade():
    raise RuntimeError('Split payment history must be preserved; restore a verified backup instead.')
