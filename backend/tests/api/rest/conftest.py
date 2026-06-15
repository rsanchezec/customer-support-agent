"""Test fixtures for REST conversations API tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base

# ---------------------------------------------------------------------------
# In-memory engine + session
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    """In-memory SQLite engine with FK enforcement."""
    from sqlalchemy import event

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
async def session_factory(engine):
    """AsyncSession factory bound to the in-memory engine."""
    maker = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )
    # Create all tables once.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return maker


@pytest.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Per-test session that rolls back after each test."""
    async with session_factory() as sess:
        yield sess
        await sess.rollback()


@pytest.fixture(autouse=True)
async def clean_tables(session: AsyncSession):
    """Delete all rows from every table after each test."""
    yield
    # FK cascade takes care of dependent tables first.
    for table in reversed(Base.metadata.sorted_tables):
        await session.execute(table.delete())
    await session.commit()
