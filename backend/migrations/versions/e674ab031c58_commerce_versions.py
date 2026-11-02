"""Use 64-bit source versions for durable event ordering."""
from alembic import op
import sqlalchemy as sa
revision = 'e674ab031c58'
down_revision = 'd5639a021b47'
branch_labels = None
depends_on = None
def upgrade():
    # SQLite INTEGER already stores signed 64-bit values. PostgreSQL INTEGER
    # is 32-bit and needs an explicit, non-destructive widening migration.
    if op.get_bind().dialect.name == 'postgresql':
        for name in ('connections', 'links', 'orders', 'inbox'):
            op.alter_column('commerce_'+name, 'version', existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=False)
def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        for name in ('connections', 'links', 'orders', 'inbox'):
            op.alter_column('commerce_'+name, 'version', existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=False)
