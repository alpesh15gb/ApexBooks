"""Add immutable company-scoped evidence, without changing existing book rows."""
from alembic import op
import sqlalchemy as sa
revision='g896cd253e70'
down_revision='f785bc142d69'
branch_labels=None
depends_on=None

def upgrade():
    op.create_index('uq_records_company_id_id','records',['company_id','id'],unique=True)
    op.create_table('document_attachments',
        sa.Column('id',sa.String(),primary_key=True),sa.Column('company_id',sa.String(),sa.ForeignKey('companies.id'),nullable=False),
        sa.Column('record_id',sa.String(),nullable=False),sa.Column('filename',sa.String(120),nullable=False),
        sa.Column('media_type',sa.String(32),nullable=False),sa.Column('size_bytes',sa.Integer(),nullable=False),
        sa.Column('sha256',sa.String(64),nullable=False),sa.Column('content',sa.LargeBinary(),nullable=False),
        sa.Column('created_by',sa.String(),sa.ForeignKey('users.id'),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('is_archived',sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column('version',sa.Integer(),nullable=False,server_default='0'),
        sa.UniqueConstraint('company_id','id'),sa.UniqueConstraint('company_id','record_id','sha256'),
        sa.ForeignKeyConstraint(['company_id','record_id'],['records.company_id','records.id']),
        sa.CheckConstraint('size_bytes > 0 AND size_bytes <= 2097152'),sa.CheckConstraint('size_bytes = length(content)'),sa.CheckConstraint('length(sha256) = 64'),sa.CheckConstraint("media_type IN ('application/pdf','image/png','image/jpeg')"),sa.CheckConstraint('version >= 0'))
    op.create_index('ix_document_attachments_company_id','document_attachments',['company_id']);op.create_index('ix_document_attachments_record_id','document_attachments',['record_id'])
    op.create_table('attachment_write_keys',sa.Column('id',sa.String(),primary_key=True),
        sa.Column('company_id',sa.String(),sa.ForeignKey('companies.id'),nullable=False),sa.Column('key',sa.String(80),nullable=False),
        sa.Column('request_hash',sa.String(64),nullable=False),sa.Column('attachment_id',sa.String(),nullable=False),
        sa.UniqueConstraint('company_id','key'),sa.ForeignKeyConstraint(['company_id','attachment_id'],['document_attachments.company_id','document_attachments.id']))
    op.create_index('ix_attachment_write_keys_company_id','attachment_write_keys',['company_id'])

def downgrade():
    op.drop_table('attachment_write_keys');op.drop_table('document_attachments');op.drop_index('uq_records_company_id_id',table_name='records')
