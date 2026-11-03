"""SQLite-only ordering-index metadata checks; no startup schema repair."""
import re
from sqlalchemy.schema import CreateIndex

SQLITE_RECORD_ORDER_INDEX='ix_records_company_order'

def include_schema_object(dialect):
    def include(obj,name,type_,reflected,compare_to):
        # ddl_if controls DDL, not Alembic metadata comparison. Exclude only this
        # dialect-specific MODEL index; unrelated/reflected objects still compare.
        return not (dialect!='sqlite' and type_=='index' and name==SQLITE_RECORD_ORDER_INDEX and not reflected and compare_to is None)
    return include

def require_unversioned_record_order_index(connection,metadata):
    if connection.dialect.name!='sqlite':return
    actual=connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type='index' AND name=?",(SQLITE_RECORD_ORDER_INDEX,)).scalar_one_or_none()
    index=next(i for i in metadata.tables['records'].indexes if i.name==SQLITE_RECORD_ORDER_INDEX)
    expected=str(CreateIndex(index).compile(dialect=connection.dialect))
    def normalize(sql):
        # Whitespace/case outside string literals is irrelevant; JSON paths and
        # defaults INSIDE literals must stay byte-exact (including spaces/case).
        return ''.join(part if i%2 else re.sub(r'\s+','',part).lower() for i,part in enumerate(re.split(r"('(?:''|[^'])*')",sql.strip().rstrip(';'))))
    if actual is None or normalize(actual)!=normalize(expected):
        raise RuntimeError('Unversioned SQLite record-order index is missing or differs from the baseline. Restore or migrate a reviewed copy before stamping; no schema was repaired.')
