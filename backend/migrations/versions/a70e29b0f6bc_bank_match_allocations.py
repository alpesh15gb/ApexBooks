"""Allow partial and many-to-many bank statement matching.

Revision ID: a70e29b0f6bc
Revises: f81703c47a62
"""
from alembic import op
import sqlalchemy as sa

revision = 'a70e29b0f6bc'
down_revision = 'f81703c47a62'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('bank_match_allocations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('company_id', sa.String(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('statement_line_id', sa.String(), sa.ForeignKey('bank_statement_lines.id'), nullable=False),
        sa.Column('record_id', sa.String(), sa.ForeignKey('records.id'), nullable=False),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False),
        sa.UniqueConstraint('company_id', 'statement_line_id', 'record_id'),
        sa.CheckConstraint('amount > 0', name='bank_match_amount_positive'),
    )
    op.create_index('ix_bank_match_allocations_company_id', 'bank_match_allocations', ['company_id'])
    op.create_index('ix_bank_match_allocations_statement_line_id', 'bank_match_allocations', ['statement_line_id'])
    op.create_index('ix_bank_match_allocations_record_id', 'bank_match_allocations', ['record_id'])


def downgrade():
    raise RuntimeError('Bank matching history must be preserved; restore a verified backup instead.')
