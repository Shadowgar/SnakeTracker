from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy.engine import make_url

from snaketracker.infrastructure.database.engine import create_sqlite_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configured_url = make_url(config.get_main_option("sqlalchemy.url"))
    configured_database = configured_url.database
    database = Path(
        os.environ.get("SNAKETRACKER_DATABASE_PATH")
        or (configured_database if configured_database is not None else "")
    )
    connectable = create_sqlite_engine(
        database,
        require_local_storage=os.environ.get("SNAKETRACKER_ENVIRONMENT") == "production",
    )
    try:
        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
