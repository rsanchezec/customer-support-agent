"""Pytest fixtures for DB model tests — in-memory SQLite, per-test rollback."""

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base


@pytest.fixture
async def engine():
    """Create an in-memory SQLite engine with FK enforcement for each test."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    @event.listens_for(eng.sync_engine, "connect")
    def set_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    yield eng

    await eng.dispose()


@pytest.fixture
async def session(engine):
    """Provide an AsyncSession that rolls back after each test."""
    async_session = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )

    async with async_session() as sess:
        # Create all tables before the test.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield sess
        await sess.rollback()


@pytest.fixture(autouse=True)
async def create_all(engine):
    """Ensure tables exist before every test that uses `session`."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
