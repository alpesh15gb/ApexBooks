"""add normalized accounting and gst tables
Revision ID: 0002_normalized_accounting
Revises: 0001_initial_e2e_engine
Create Date: 2026-05-13
"""
from alembic import op
from app.models.accounting import PartyModel, ItemModel, InvoiceModel, InvoiceLineModel, PaymentModel, GLEntryModel, GSTReturnModel

revision = '0002_normalized_accounting'
down_revision = '0001_initial_e2e_engine'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    for table in [
        PartyModel.__table__, ItemModel.__table__, InvoiceModel.__table__,
        InvoiceLineModel.__table__, PaymentModel.__table__, GLEntryModel.__table__,
        GSTReturnModel.__table__,
    ]:
        table.create(bind, checkfirst=True)

def downgrade():
    bind = op.get_bind()
    for table in [
        GSTReturnModel.__table__, GLEntryModel.__table__, PaymentModel.__table__,
        InvoiceLineModel.__table__, InvoiceModel.__table__, ItemModel.__table__,
        PartyModel.__table__,
    ]:
        table.drop(bind, checkfirst=True)
