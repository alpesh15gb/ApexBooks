"""TEST ONLY: SQLite preseeded company generation. Never imported by the app.

Not a release design: new shared-row lock ordering, no
PostgreSQL concurrency proof, and no coverage for clock-derived responses.
"""
from sqlalchemy import inspect

COVERED = frozenset('''companies company_members company_preferences company_tax_profiles
records ledger_accounts bank_accounts journals journal_lines journal_reversals period_locks
record_postings document_conversions payment_allocations payment_split_allocations
bank_statement_lines bank_match_allocations bank_reconciliation_reviews stock_movements
number_series document_attachments commerce_connections commerce_links commerce_orders
commerce_reservations commerce_inbox commerce_outbox commerce_reconciliations'''.split())
EXCLUDED = {
 'users':'global account/authentication state',
 'auth_sessions':'global session authorization; recheck every detection request',
 'auth_recovery_codes':'global account authentication',
 'auth_rate_buckets':'global authentication throttle',
 'audit_events':'audit view is outside this persisted-domain token; export reads append audit',
 'idempotency_keys':'operational replay binding, not company business state',
 'journal_commands':'operational replay binding',
 'attachment_write_keys':'operational replay binding',
 'backup_jobs':'user/global transfer state; nullable company scope',
 'backup_chunks':'staging bytes owned by job, not retained evidence',
 'backup_storage_budget':'global transfer reservation quota',
 'alembic_version':'schema lifecycle, checked separately',
}
TABLE='poc_company_generation'
def quote(name):return '"'+name.replace('"','""')+'"'
def names():return {f'poc_change_{name}_{event}' for name in COVERED for event in ('insert','update','delete')}
def schema_check(connection, metadata):
    actual=set(inspect(connection).get_table_names())-{TABLE}
    expected=COVERED|set(EXCLUDED)
    if actual!=expected:raise ValueError(f'Unclassified or missing tables: {sorted(actual^expected)}')
    if set(metadata.tables)!=expected-{'alembic_version'}:raise ValueError('Model table coverage changed')
    for name in COVERED:
        if ('id' if name=='companies' else 'company_id') not in metadata.tables[name].c:raise ValueError('Missing company identity: '+name)
def install(connection,metadata):
    if connection.dialect.name!='sqlite':raise ValueError('SQLite proof only; PostgreSQL is unexecuted and not installed')
    schema_check(connection,metadata)
    connection.exec_driver_sql(f'CREATE TABLE {TABLE} (company_id TEXT PRIMARY KEY, generation INTEGER NOT NULL CHECK(generation>=0 AND generation<9223372036854775807))')
    connection.exec_driver_sql(f'INSERT INTO {TABLE}(company_id,generation) SELECT id,0 FROM companies')
    for sql in trigger_definitions(metadata):connection.exec_driver_sql(sql)
    readiness(connection,metadata)
def trigger_definitions(metadata):
    definitions=[]
    # No FK and no lazy upsert: avoid acquiring Company FK locks on a first write.
    # This still introduces a shared generation-row lock on PostgreSQL. UNVERIFIED.
    for name in sorted(COVERED):
        key='id' if name=='companies' else 'company_id';new='NEW.'+quote(key);old='OLD.'+quote(key)
        def bump(scope,condition='1'):
            return f"SELECT CASE WHEN ({condition}) AND NOT EXISTS(SELECT 1 FROM {TABLE} WHERE company_id={scope}) THEN RAISE(ABORT,'Missing experimental company generation') END; UPDATE {TABLE} SET generation=generation+1 WHERE company_id={scope} AND ({condition});"
        for event,scope in [('insert',new),('delete',old)]:
            body=(f'INSERT INTO {TABLE}(company_id,generation) VALUES({new},0);' if name=='companies' and event=='insert' else '')+bump(scope)
            definitions.append(f'CREATE TRIGGER {quote("poc_change_"+name+"_"+event)} AFTER {event.upper()} ON {quote(name)} BEGIN {body} END')
        changed=' OR '.join('OLD.'+quote(c.name)+' IS NOT NEW.'+quote(c.name) for c in metadata.tables[name].columns)
        body=bump(new)+bump(old,old+' IS NOT '+new)
        definitions.append(f'CREATE TRIGGER {quote("poc_change_"+name+"_update")} AFTER UPDATE ON {quote(name)} WHEN {changed} BEGIN {body} END')
    return definitions
def readiness(connection,metadata):
    schema_check(connection,metadata)
    found=dict(connection.exec_driver_sql("SELECT name,sql FROM sqlite_master WHERE type='trigger'").all())
    required=names()
    if not required<=set(found):raise ValueError('Missing proof triggers: '+str(sorted(required-set(found))))
    for sql in trigger_definitions(metadata):
        name=sql.split(chr(34))[1]
        if found[name].strip().rstrip(';')!=sql.strip().rstrip(';'):raise ValueError('Changed proof trigger definition: '+name)
    if inspect(connection).get_foreign_keys(TABLE):raise ValueError('Proof counter must not add a parent lock dependency')
    missing=connection.exec_driver_sql(f'SELECT COUNT(*) FROM companies c LEFT JOIN {TABLE} g ON g.company_id=c.id WHERE g.company_id IS NULL').scalar_one()
    if missing:raise ValueError('Unseeded company generation')
def token(connection,cid):
    return connection.exec_driver_sql(f'SELECT generation FROM {TABLE} WHERE company_id=?',(cid,)).scalar_one()
def uninstall(connection):
    for name in names():connection.exec_driver_sql('DROP TRIGGER IF EXISTS '+quote(name))
    connection.exec_driver_sql('DROP TABLE IF EXISTS '+TABLE)
