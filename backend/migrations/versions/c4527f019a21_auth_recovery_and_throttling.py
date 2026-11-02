"""Add one-use account recovery codes and persistent auth throttles."""
from alembic import op
import sqlalchemy as sa
revision='c4527f019a21'
down_revision='b3486c812f14'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('auth_recovery_codes',sa.Column('digest',sa.String(64),primary_key=True),sa.Column('user_id',sa.String(),sa.ForeignKey('users.id'),nullable=False),sa.Column('used_at',sa.DateTime(timezone=True),nullable=True))
    op.create_index('ix_auth_recovery_codes_user_id','auth_recovery_codes',['user_id'])
    op.create_table('auth_rate_buckets',sa.Column('key',sa.String(64),primary_key=True),sa.Column('started_at',sa.DateTime(timezone=True),nullable=False),sa.Column('attempts',sa.Integer(),nullable=False))
    op.create_index('ix_auth_rate_buckets_started_at','auth_rate_buckets',['started_at'])
def downgrade():
    op.drop_table('auth_rate_buckets');op.drop_table('auth_recovery_codes')
