"""Add durable bounded import/export staging, separate from retained evidence."""
from alembic import op
import sqlalchemy as sa
revision='h907ef475a92'
down_revision='g896cd253e70'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('backup_jobs',sa.Column('id',sa.String(),primary_key=True),sa.Column('user_id',sa.String(),sa.ForeignKey('users.id'),nullable=False),sa.Column('company_id',sa.String(),sa.ForeignKey('companies.id'),nullable=True),sa.Column('direction',sa.String(8),nullable=False),sa.Column('state',sa.String(16),nullable=False),sa.Column('company_name',sa.String(120),nullable=False),sa.Column('request_key',sa.String(80),nullable=False),sa.Column('request_hash',sa.String(64),nullable=False),sa.Column('byte_count',sa.BigInteger(),nullable=False),sa.Column('sha256',sa.String(64),nullable=False),sa.Column('reserved_bytes',sa.BigInteger(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('report',sa.JSON(),nullable=False),sa.Column('restored_company_id',sa.String(),sa.ForeignKey('companies.id'),nullable=True),sa.UniqueConstraint('user_id','request_key'),sa.CheckConstraint('byte_count >= 0 AND reserved_bytes >= 0'))
    for field in ('user_id','company_id','expires_at'):op.create_index('ix_backup_jobs_'+field,'backup_jobs',[field])
    op.create_table('backup_chunks',sa.Column('job_id',sa.String(),sa.ForeignKey('backup_jobs.id',ondelete='CASCADE'),primary_key=True),sa.Column('chunk_index',sa.Integer(),primary_key=True),sa.Column('size_bytes',sa.Integer(),nullable=False),sa.Column('sha256',sa.String(64),nullable=False),sa.Column('content',sa.LargeBinary(),nullable=False),sa.CheckConstraint('chunk_index >= 0 AND size_bytes > 0 AND size_bytes <= 524288 AND size_bytes = length(content) AND length(sha256) = 64'))
    budget=op.create_table('backup_storage_budget',sa.Column('id',sa.String(32),primary_key=True),sa.Column('reserved_bytes',sa.BigInteger(),nullable=False),sa.CheckConstraint('reserved_bytes >= 0'))
    op.bulk_insert(budget,[{'id':'global','reserved_bytes':0}])

def downgrade():
    op.drop_table('backup_chunks');op.drop_table('backup_jobs');op.drop_table('backup_storage_budget')
