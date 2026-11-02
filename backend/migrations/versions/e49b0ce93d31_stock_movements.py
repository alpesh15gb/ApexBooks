"""Track quantities for explicitly linked stock items.

Revision ID: e49b0ce93d31
Revises: c321f06d1a48
"""
from alembic import op
import sqlalchemy as sa

revision = 'e49b0ce93d31'
down_revision = 'c321f06d1a48'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('stock_movements',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('company_id', sa.String(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('item_id', sa.String(), sa.ForeignKey('records.id'), nullable=False),
        sa.Column('source_record_id', sa.String(), sa.ForeignKey('records.id'), nullable=False),
        sa.Column('line_index', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('quantity', sa.Numeric(15, 3), nullable=False),
        sa.UniqueConstraint('company_id', 'source_record_id', 'line_index'),
    )
    op.create_index('ix_stock_movements_company_id', 'stock_movements', ['company_id'])
    op.create_index('ix_stock_movements_item_id', 'stock_movements', ['item_id'])


def downgrade():
    raise RuntimeError('Stock movement history must be preserved; restore a verified backup instead.')
