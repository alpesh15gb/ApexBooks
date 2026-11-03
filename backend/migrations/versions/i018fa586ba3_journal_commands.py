"""Add durable route-scoped manual journal retry bindings without changing books."""
from alembic import op
import sqlalchemy as sa
revision='i018fa586ba3'
down_revision='h907ef475a92'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('journal_commands',
        sa.Column('id',sa.String(),primary_key=True),
        sa.Column('company_id',sa.String(),sa.ForeignKey('companies.id'),nullable=False),
        sa.Column('operation',sa.String(128),nullable=False),
        sa.Column('key',sa.String(80),nullable=False),
        sa.Column('request_hash',sa.String(64),nullable=False),
        sa.Column('journal_id',sa.String(),nullable=False),
        sa.Column('response',sa.JSON(),nullable=False),
        sa.UniqueConstraint('company_id','operation','key'),
        sa.ForeignKeyConstraint(['company_id','journal_id'],['journals.company_id','journals.id']))
    op.create_index('ix_journal_commands_company_id','journal_commands',['company_id'])

def downgrade():
    # Silently removing successful retry bindings can cause duplicate financial
    # operations after rollback. Only an empty additive table may be removed.
    if op.get_context().as_sql:
        raise RuntimeError('Journal command downgrade requires an online empty-table check')
    bind=op.get_bind()
    if bind.dialect.name=='postgresql':
        bind.execute(sa.text('LOCK TABLE journal_commands IN ACCESS EXCLUSIVE MODE'))
    elif bind.dialect.name=='sqlite':
        # Force a write transaction before reading emptiness. SQLite's legacy
        # SELECT alone does not reserve the writer; a command could otherwise
        # commit after COUNT and be silently removed by DROP.
        bind.execute(sa.text('UPDATE journal_commands SET key=key WHERE 1=0'))
    else:
        raise RuntimeError('Journal command downgrade supports only reviewed PostgreSQL or SQLite locking')
    if bind.execute(sa.text('SELECT COUNT(*) FROM journal_commands')).scalar():
        raise RuntimeError('Cannot downgrade while journal retry bindings exist; keep this additive schema or restore a reviewed backup')
    op.drop_index('ix_journal_commands_company_id',table_name='journal_commands')
    op.drop_table('journal_commands')
