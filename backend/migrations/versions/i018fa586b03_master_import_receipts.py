"""Persist exact keyed master import results independently of company backups."""
from alembic import op
import sqlalchemy as sa
revision='i018fa586b03'
down_revision='h907ef475a92'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('master_import_receipts',
        sa.Column('id',sa.String(),primary_key=True),
        sa.Column('company_id',sa.String(),sa.ForeignKey('companies.id'),nullable=False),
        sa.Column('actor_id',sa.String(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('operation_key',sa.String(80),nullable=False),
        sa.Column('request_hash',sa.String(64),nullable=False),
        sa.Column('response',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('company_id','operation_key'))
    op.create_index('ix_master_import_receipts_company_id','master_import_receipts',['company_id'])

def downgrade():
    # Dropping accepted keys could turn a later retry into a new import.
    connection=op.get_bind()
    if connection.execute(sa.text('SELECT COUNT(*) FROM master_import_receipts')).scalar():
        raise RuntimeError('Cannot downgrade with retained import receipts; preserve recovery history and use a reviewed rollback plan')
    op.drop_table('master_import_receipts')
