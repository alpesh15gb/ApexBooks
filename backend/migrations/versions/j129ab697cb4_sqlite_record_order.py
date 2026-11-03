"""Index existing SQLite record order; PostgreSQL data/query/indexes unchanged."""
from alembic import op
revision='j129ab697cb4'
down_revision='i018fa586ba3'
branch_labels=None
depends_on=None

def upgrade():
    if op.get_bind().dialect.name=='sqlite':
        # Frozen SQL, no runtime imports or user-controlled identifiers/paths.
        op.execute('CREATE INDEX ix_records_company_order ON records '
                   '(company_id, date DESC, coalesce(json_extract(data, \'$."created_at"\'), \'\') DESC, id DESC)')

def downgrade():
    if op.get_bind().dialect.name=='sqlite':
        op.execute('DROP INDEX ix_records_company_order')
