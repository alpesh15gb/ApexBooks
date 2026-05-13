"""initial e2e engine tables
Revision ID: 0001_initial_e2e_engine
Revises: 
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa
revision='0001_initial_e2e_engine'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('companies_registry', sa.Column('company_id', sa.String(64), primary_key=True), sa.Column('company_name', sa.String(255), nullable=False), sa.Column('gstin', sa.String(15), nullable=False, unique=True), sa.Column('pan', sa.String(10)), sa.Column('state_code', sa.String(2), nullable=False), sa.Column('payload', sa.JSON(), nullable=False), sa.Column('schema_name', sa.String(64), nullable=False), sa.Column('created_at', sa.DateTime()), sa.Column('updated_at', sa.DateTime()))
    op.create_table('users_registry', sa.Column('user_id', sa.String(64), primary_key=True), sa.Column('tenant_id', sa.String(64), index=True), sa.Column('email', sa.String(255), unique=True), sa.Column('full_name', sa.String(255)), sa.Column('password_hash', sa.String(255)), sa.Column('roles', sa.JSON()), sa.Column('permissions', sa.JSON()), sa.Column('is_active', sa.Boolean()), sa.Column('created_at', sa.DateTime()))
    op.create_table('api_keys', sa.Column('key_id', sa.String(64), primary_key=True), sa.Column('tenant_id', sa.String(64), index=True), sa.Column('name', sa.String(255)), sa.Column('key_hash', sa.String(255)), sa.Column('is_active', sa.Boolean()), sa.Column('created_at', sa.DateTime()))
    op.create_table('tenant_resources', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('tenant_id', sa.String(64), index=True), sa.Column('resource', sa.String(64), index=True), sa.Column('resource_id', sa.String(64), index=True), sa.Column('payload', sa.JSON()), sa.Column('status', sa.String(64)), sa.Column('txn_date', sa.Date()), sa.Column('amount', sa.Numeric(14,2)), sa.Column('is_deleted', sa.Boolean()), sa.Column('created_at', sa.DateTime()), sa.Column('updated_at', sa.DateTime()), sa.UniqueConstraint('tenant_id','resource','resource_id', name='uq_tenant_resource_id'))
    op.create_table('numbering_series', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('tenant_id', sa.String(64), index=True), sa.Column('series_key', sa.String(64)), sa.Column('prefix', sa.String(32)), sa.Column('current', sa.Integer()), sa.Column('padding', sa.Integer()), sa.UniqueConstraint('tenant_id','series_key', name='uq_tenant_series'))
    op.create_table('audit_logs', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('tenant_id', sa.String(64), index=True), sa.Column('actor_id', sa.String(64)), sa.Column('action', sa.String(64)), sa.Column('resource', sa.String(64)), sa.Column('resource_id', sa.String(64)), sa.Column('ip_address', sa.String(64)), sa.Column('user_agent', sa.Text()), sa.Column('details', sa.JSON()), sa.Column('created_at', sa.DateTime()))

def downgrade():
    for t in ['audit_logs','numbering_series','tenant_resources','api_keys','users_registry','companies_registry']:
        op.drop_table(t)
