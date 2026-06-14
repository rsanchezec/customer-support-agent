"""Unit tests for ConversationService.

All tests use an in-memory SQLite database with per-test rollback.
No live Foundry or Entra endpoint is contacted.
"""

from __future__ import annotations

import uuid
from datetime import UTC

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.domain.conversation import Conversation
from app.domain.user import User
from app.services.conversation_service import (
    ConversationNotFoundError,
    ConversationService,
)

# ---------------------------------------------------------------------------
# In-memory engine + session fixtures (same pattern as tests/db/conftest.py)
# ---------------------------------------------------------------------------


@pytest.fixture
async def csvc_engine():
    """In-memory SQLite engine with FK enforcement per test."""
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
async def csvc_session_maker(csvc_engine):
    """AsyncSession factory bound to the in-memory engine."""
    maker = async_sessionmaker(
        bind=csvc_engine,
        expire_on_commit=False,
        autoflush=False,
    )
    async with csvc_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return maker


@pytest.fixture
async def csvc_session(csvc_session_maker):
    """Provide an AsyncSession for the test (tables already created)."""
    async with csvc_session_maker() as sess:
        yield sess


@pytest.fixture
async def conv_service(csvc_session_maker):
    """ConversationService backed by the session factory."""
    return ConversationService(csvc_session_maker)


# ---------------------------------------------------------------------------
# Helper builders (operate on the test's own session)
# ---------------------------------------------------------------------------


async def make_user(sess: AsyncSession, oid: str = "oid-123") -> User:
    """Insert a User row and return it."""
    user = User(entraid_oid=oid, email="test@example.com", display_name="Test User")
    sess.add(user)
    await sess.commit()
    await sess.refresh(user)
    return user


async def make_conversation(
    sess: AsyncSession, user: User, title: str | None = None
) -> Conversation:
    """Insert a Conversation row and return it."""
    conv = Conversation(user_id=user.id, title=title)
    sess.add(conv)
    await sess.commit()
    await sess.refresh(conv)
    return conv


# ---------------------------------------------------------------------------
# get_or_create tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_create_creates_new_when_no_id(conv_service, csvc_session):
    """When conversation_id is None, a brand-new row is inserted."""
    user = await make_user(csvc_session)

    conv, created = await conv_service.get_or_create(
        user=user, conversation_id=None, session=csvc_session
    )

    assert created is True
    assert conv.user_id == user.id
    assert conv.foundry_conversation_id is None
    assert conv.title is None


@pytest.mark.asyncio
async def test_get_or_create_returns_existing_when_id_matches(conv_service, csvc_session):
    """When a valid conversation_id is supplied, the existing row is returned."""
    user = await make_user(csvc_session)
    existing = await make_conversation(csvc_session, user, title="My conversation")

    conv, created = await conv_service.get_or_create(
        user=user, conversation_id=existing.id, session=csvc_session
    )

    assert created is False
    assert conv.id == existing.id
    assert conv.title == "My conversation"


@pytest.mark.asyncio
async def test_get_or_create_scopes_to_user(conv_service, csvc_session):
    """A user cannot fetch another user's conversation — raises NotFoundError."""
    user_a = await make_user(csvc_session, oid="oid-a")
    user_b = await make_user(csvc_session, oid="oid-b")
    conv_b = await make_conversation(csvc_session, user_b)

    with pytest.raises(ConversationNotFoundError) as exc_info:
        await conv_service.get_or_create(
            user=user_a, conversation_id=conv_b.id, session=csvc_session
        )

    assert exc_info.value.conversation_id == conv_b.id


@pytest.mark.asyncio
async def test_get_or_create_raises_when_id_not_found(conv_service, csvc_session):
    """Passing a non-existent conversation_id raises ConversationNotFoundError."""
    user = await make_user(csvc_session)
    random_id = uuid.uuid4()

    with pytest.raises(ConversationNotFoundError) as exc_info:
        await conv_service.get_or_create(user=user, conversation_id=random_id, session=csvc_session)

    assert exc_info.value.conversation_id == random_id


# ---------------------------------------------------------------------------
# link_foundry_session tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_foundry_session_persists_id(conv_service, csvc_session):
    """link_foundry_session writes the foundry_conversation_id to the database."""
    user = await make_user(csvc_session)
    conv = await make_conversation(csvc_session, user)

    updated = await conv_service.link_foundry_session(conv, "f-sid-001", session=csvc_session)

    assert updated.foundry_conversation_id == "f-sid-001"

    # Verify it persisted by re-fetching.
    from sqlalchemy import select

    row = await csvc_session.execute(select(Conversation).where(Conversation.id == conv.id))
    stored = row.scalar_one()
    assert stored.foundry_conversation_id == "f-sid-001"


@pytest.mark.asyncio
async def test_link_foundry_session_is_idempotent(conv_service, csvc_session):
    """Linking the same session id twice is a no-op (idempotent)."""
    user = await make_user(csvc_session)
    conv = await make_conversation(csvc_session, user)

    result1 = await conv_service.link_foundry_session(conv, "f-sid-001", session=csvc_session)
    result2 = await conv_service.link_foundry_session(conv, "f-sid-001", session=csvc_session)

    assert result1.foundry_conversation_id == result2.foundry_conversation_id == "f-sid-001"


# ---------------------------------------------------------------------------
# list_for_user tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_for_user_returns_recent_first(conv_service, csvc_session):
    """list_for_user returns conversations ordered by created_at descending."""
    from datetime import datetime, timedelta

    user = await make_user(csvc_session)
    now = datetime.now(UTC)
    # conv_a is oldest, conv_c is newest — set explicit timestamps before insert.
    conv_a = Conversation(user_id=user.id, title="First", created_at=now - timedelta(hours=2))
    conv_b = Conversation(user_id=user.id, title="Second", created_at=now - timedelta(hours=1))
    conv_c = Conversation(user_id=user.id, title="Third", created_at=now)
    csvc_session.add_all([conv_a, conv_b, conv_c])
    await csvc_session.commit()
    await csvc_session.refresh(conv_a)
    await csvc_session.refresh(conv_b)
    await csvc_session.refresh(conv_c)

    results = await conv_service.list_for_user(user=user, session=csvc_session)

    # Most recent (conv_c) should be first.
    assert [r.id for r in results] == [conv_c.id, conv_b.id, conv_a.id]


@pytest.mark.asyncio
async def test_list_for_user_respects_limit(conv_service, csvc_session):
    """list_for_user returns at most ``limit`` rows."""
    user = await make_user(csvc_session)
    for i in range(5):
        await make_conversation(csvc_session, user, title=f"Conv {i}")

    results = await conv_service.list_for_user(user=user, limit=3, session=csvc_session)

    assert len(results) == 3


@pytest.mark.asyncio
async def test_list_for_user_excludes_other_user(conv_service, csvc_session):
    """Conversations belonging to other users are not returned."""
    user_a = await make_user(csvc_session, oid="oid-a")
    user_b = await make_user(csvc_session, oid="oid-b")
    await make_conversation(csvc_session, user_a, title="A's conv")
    await make_conversation(csvc_session, user_b, title="B's conv")

    results = await conv_service.list_for_user(user=user_a, session=csvc_session)

    assert all(r.user_id == user_a.id for r in results)
    assert len(results) == 1


# ---------------------------------------------------------------------------
# set_title tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_title_truncates_to_255(conv_service, csvc_session):
    """set_title silently truncates titles longer than 255 characters."""
    user = await make_user(csvc_session)
    conv = await make_conversation(csvc_session, user)

    long_title = "A" * 300
    updated = await conv_service.set_title(conv, long_title, session=csvc_session)

    assert len(updated.title) == 255
    assert updated.title == "A" * 255


@pytest.mark.asyncio
async def test_set_title_clears_title(conv_service, csvc_session):
    """Passing an empty string clears the title (sets to None)."""
    user = await make_user(csvc_session)
    conv = await make_conversation(csvc_session, user, title="Old title")

    updated = await conv_service.set_title(conv, "", session=csvc_session)

    assert updated.title is None


@pytest.mark.asyncio
async def test_set_title_preserves_short_titles(conv_service, csvc_session):
    """Titles at or under 255 characters are stored unchanged."""
    user = await make_user(csvc_session)
    conv = await make_conversation(csvc_session, user)

    short_title = "Hello, world!"
    updated = await conv_service.set_title(conv, short_title, session=csvc_session)

    assert updated.title == short_title
