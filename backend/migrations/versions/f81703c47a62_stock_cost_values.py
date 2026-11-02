"""Record moving-average cost for new tracked stock movements.

Existing movements remain NULL and require a reviewed valuation migration.

Revision ID: f81703c47a62
Revises: e49b0ce93d31
"""
from alembic import op
import sqlalchemy as sa

revision = 'f81703c47a62'
down_revision = 'e49b0ce93d31'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('stock_movements') as batch:
        batch.add_column(sa.Column('cost_value', sa.Numeric(15, 2), nullable=True))


def downgrade():
    raise RuntimeError('Stock valuation history must be preserved; restore a verified backup instead.')
