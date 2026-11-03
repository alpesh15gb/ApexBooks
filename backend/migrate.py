"""Apply versioned schema migrations before serving API requests.

An unversioned database from the early prototype is stamped only when its
tables and columns match the current baseline. Any other shape requires a
reviewed data migration; startup refuses to guess.
"""
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from main import Base, engine
from record_order import include_schema_object, require_unversioned_record_order_index


def run_migrations():
    config = Config(str(Path(__file__).with_name('alembic.ini')))
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    if existing and 'alembic_version' not in existing:
        with engine.connect() as connection:
            require_unversioned_record_order_index(connection, Base.metadata)
            differences = compare_metadata(MigrationContext.configure(connection, opts={'compare_type': True, 'include_object': include_schema_object(connection.dialect.name)}), Base.metadata)
        if differences:
            raise RuntimeError(f'Unversioned database schema differs from the baseline ({len(differences)} differences). Restore or migrate a copy before starting.')
        command.stamp(config, 'head')
    else:
        command.upgrade(config, 'head')


if __name__ == '__main__':
    run_migrations()
