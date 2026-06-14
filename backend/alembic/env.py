"""Async Alembic environment.

Reads DATABASE_URL from app.settings.Settings so that alembic.ini can leave
sqlalchemy.url empty (avoids duplicating the connection string).
Supports both online (async) and offline (emit SQL) modes.
"""

from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.db.base import Base
from app.settings import Settings

# Alembic Config object.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the database URL programmatically from Settings.
settings = Settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# Add your model's MetaData object here for 'autogenerate' support.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL only)."""
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode (async connection)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_migrations_sync)

    await connectable.dispose()


def do_migrations_sync(connection) -> None:
    """Run migrations synchronously inside run_sync()."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


# Decide which mode based on whether a connection URL is present.
# Offline mode is triggered by `alembic migration ... --sql`.
if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
