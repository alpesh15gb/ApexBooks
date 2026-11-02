"""Read-only release gate; schema changes are applied by the migration command."""
from functools import lru_cache
from pathlib import Path
from threading import Lock
from weakref import WeakKeyDictionary
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

_verified=WeakKeyDictionary()
_lock=Lock()

@lru_cache(maxsize=1)
def required_revision():
    return ScriptDirectory(str(Path(__file__).with_name('migrations'))).get_current_head()

def schema_ready(engine):
    with _lock:
        if _verified.get(engine): return True
        try:
            with engine.connect() as connection:
                versions=set(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
                required={'commerce_connections','commerce_links','commerce_orders','commerce_reservations','commerce_inbox','commerce_outbox','commerce_reconciliations'}
                ready=versions=={required_revision()} and required.issubset(inspect(connection).get_table_names())
        except SQLAlchemyError:
            return False
        if ready: _verified[engine]=True
        return ready
