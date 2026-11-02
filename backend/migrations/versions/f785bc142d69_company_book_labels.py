"""Add an owner-chosen book label separate from the legal company name."""
from alembic import op
import sqlalchemy as sa
revision='f785bc142d69'
down_revision='e674ab031c58'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('companies',sa.Column('book_label',sa.String(80),nullable=False,server_default=''))

def downgrade():
    op.drop_column('companies','book_label')
