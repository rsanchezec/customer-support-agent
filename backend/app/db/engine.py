"""Async SQLAlchemy engine factory.

Lazily creates the async engine on first call, then caches it.
SQLite connections enable WAL mode and foreign-key enforcement.
"""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.settings import Settings

settings = Settings()

_engine: AsyncEngine | None = None


def _setup_sqlite_pragma(dbapi_conn: object) -> None:
    """Enable WAL mode and foreign-key enforcement on new SQLite connections."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine() -> AsyncEngine:
    """Return the cached async engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.app_env == "dev",
        )
        event.listen(_engine.sync_engine, "connect", _setup_sqlite_pragma)
    return _engine


# Module-level engine reference for import by other infrastructure modules.
async_engine = get_engine()
