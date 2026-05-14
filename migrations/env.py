from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from app.models.base import Base

# Import all models so migrations detect schema changes
from app.models import core  # noqa
from app.models import accounting  # noqa
from app.models import e2e  # noqa

config = context.config

# Use DATABASE_URL from .env when running in Docker (overrides alembic.ini)
import os
db_url = os.environ.get('DATABASE_URL')
if db_url:
    config.set_main_option('sqlalchemy.url', db_url)

if config.config_file_name:
    try:
        fileConfig(config.config_file_name)
    except Exception:
        pass  # Skip logging config if sections are missing

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=config.get_main_option('sqlalchemy.url'),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()