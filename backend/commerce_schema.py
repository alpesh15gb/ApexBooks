"""Version-one commerce schema. Tenant is the owning account in the existing ACL model.

Keep this factory immutable: migration d5639a021b47 uses the same frozen definition.
Later schema changes belong in a new migration, not in this factory.
"""
import sqlalchemy as sa

def schema_current(metadata):
    tables = schema_v1(metadata)
    for key in ('connections', 'links', 'orders', 'inbox'):
        tables[key].c.version.type = sa.BigInteger()
    return tables


def schema_v1(metadata):
    tables = {}
    def identity():
        return [sa.Column('id', sa.String(36), primary_key=True),
                sa.Column('tenant_id', sa.String, sa.ForeignKey('users.id'), nullable=False),
                sa.Column('company_id', sa.String, sa.ForeignKey('companies.id'), nullable=False)]
    tables['connections'] = sa.Table('commerce_connections', metadata, *identity(),
        sa.Column('name', sa.String(100), nullable=False), sa.Column('base_url', sa.String(500), nullable=False),
        sa.Column('channel', sa.String(100), nullable=False), sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('secret', sa.Text, nullable=False), sa.Column('status', sa.String(16), nullable=False),
        sa.Column('config', sa.JSON, nullable=False), sa.Column('version', sa.Integer, nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False), sa.Column('updated_at', sa.String(40), nullable=False),
        sa.UniqueConstraint('tenant_id', 'company_id', 'id'),
        sa.UniqueConstraint('base_url', 'channel'),
        sa.CheckConstraint("status IN ('draft','active','paused')", name='commerce_connection_status'))
    def child(key, *columns, constraints=()):
        tables[key] = sa.Table('commerce_' + key, metadata, *identity(),
            sa.Column('connection_id', sa.String(36), nullable=False), *columns,
            sa.ForeignKeyConstraint(['tenant_id', 'company_id', 'connection_id'],
                ['commerce_connections.tenant_id', 'commerce_connections.company_id', 'commerce_connections.id']),
            *constraints)
    child('links', sa.Column('entity_type', sa.String(24), nullable=False),
        sa.Column('external_id', sa.String(160), nullable=False), sa.Column('record_id', sa.String, sa.ForeignKey('records.id')),
        sa.Column('sku', sa.String(100)), sa.Column('version', sa.Integer, nullable=False),
        sa.Column('snapshot', sa.JSON, nullable=False),
        constraints=[sa.UniqueConstraint('connection_id', 'entity_type', 'external_id'),
                     sa.UniqueConstraint('connection_id', 'sku')])
    child('orders', sa.Column('external_id', sa.String(160), nullable=False),
        sa.Column('number', sa.String(160), nullable=False), sa.Column('version', sa.Integer, nullable=False),
        sa.Column('status', sa.String(40), nullable=False), sa.Column('party_id', sa.String, sa.ForeignKey('records.id')),
        sa.Column('amount', sa.Numeric(15, 2), nullable=False), sa.Column('snapshot', sa.JSON, nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False),
        constraints=[sa.UniqueConstraint('connection_id', 'external_id')])
    child('reservations', sa.Column('reference', sa.String(160), nullable=False),
        sa.Column('status', sa.String(20), nullable=False), sa.Column('expires_at', sa.String(40), nullable=False),
        sa.Column('lines', sa.JSON, nullable=False), sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('order_id', sa.String(160)), sa.Column('updated_at', sa.String(40), nullable=False),
        constraints=[sa.UniqueConstraint('connection_id', 'reference'),
                     sa.CheckConstraint("status IN ('held','confirmed','consumed','released','expired')", name='commerce_reservation_status')])
    child('inbox', sa.Column('event_id', sa.String(160), nullable=False),
        sa.Column('event_type', sa.String(40), nullable=False), sa.Column('entity_id', sa.String(160), nullable=False),
        sa.Column('version', sa.Integer, nullable=False), sa.Column('payload', sa.JSON, nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False), sa.Column('status', sa.String(20), nullable=False),
        sa.Column('attempts', sa.Integer, nullable=False), sa.Column('available_at', sa.String(40), nullable=False),
        sa.Column('lease_until', sa.String(40)), sa.Column('error', sa.String(500), nullable=False),
        sa.Column('result', sa.JSON, nullable=False), sa.Column('created_at', sa.String(40), nullable=False),
        constraints=[sa.UniqueConstraint('connection_id', 'event_id')])
    child('outbox', sa.Column('command_id', sa.String(100), nullable=False),
        sa.Column('operation', sa.String(40), nullable=False), sa.Column('payload', sa.JSON, nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False), sa.Column('status', sa.String(20), nullable=False),
        sa.Column('attempts', sa.Integer, nullable=False), sa.Column('available_at', sa.String(40), nullable=False),
        sa.Column('lease_until', sa.String(40)), sa.Column('error', sa.String(500), nullable=False),
        sa.Column('result', sa.JSON, nullable=False), sa.Column('created_at', sa.String(40), nullable=False),
        constraints=[sa.UniqueConstraint('connection_id', 'command_id')])
    child('reconciliations', sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('status', sa.String(20), nullable=False), sa.Column('report', sa.JSON, nullable=False))
    sa.Index('ix_commerce_inbox_work', tables['inbox'].c.status, tables['inbox'].c.available_at)
    sa.Index('ix_commerce_outbox_work', tables['outbox'].c.status, tables['outbox'].c.available_at)
    sa.Index('ix_commerce_reservations_scope', tables['reservations'].c.company_id, tables['reservations'].c.status)
    return tables
