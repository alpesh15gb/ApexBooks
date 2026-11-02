"""Tenant/company scoped Bagisto connections, durable delivery and stock holds."""
from alembic import op
import sqlalchemy as sa
from commerce_schema import schema_v1

revision = 'd5639a021b47'
down_revision = 'c4527f019a21'
branch_labels = None
depends_on = None

def upgrade():
    metadata = sa.MetaData()
    for name in ('users', 'companies', 'records'):
        sa.Table(name, metadata, sa.Column('id', sa.String, primary_key=True))
    tables = schema_v1(metadata)
    metadata.create_all(op.get_bind(), tables=list(tables.values()), checkfirst=False)

def downgrade():
    for name in ('reconciliations', 'outbox', 'inbox', 'reservations', 'orders', 'links', 'connections'):
        op.drop_table('commerce_' + name)
