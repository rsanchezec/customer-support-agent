"""Tests for the /conversations REST endpoints."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.domain.conversation import Conversation
from app.domain.message import Message
from app.domain.user import User
from app.services.conversation_service import ConversationService

# ---------------------------------------------------------------------------
# Shared engine / session fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    """In-memory SQLite engine with FK enforcement."""
    from sqlalchemy import event

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(eng.sync_engine, "connect")
    def set_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine):
    maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return maker


@pytest.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as sess:
        yield sess
        await sess.rollback()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@pytest.fixture
async def user_a(session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        entraid_oid="test-oid-a",
        email="a@test.com",
        display_name="User A",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def user_b(session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        entraid_oid="test-oid-b",
        email="b@test.com",
        display_name="User B",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Test client via dependency overrides
# ---------------------------------------------------------------------------


async def make_client(
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
) -> AsyncGenerator[tuple[AsyncClient, ConversationService], None]:
    """Build an AsyncClient with dependency overrides for testing."""
    from app.api.auth.deps import get_conversation_service, get_current_user
    from app.db.session import get_session
    from app.main import create_app
    from app.settings import Settings

    svc = ConversationService(session_factory=session_factory)

    async def override_get_current_user() -> User:
        return user

    async def override_get_session() -> AsyncSession:
        async with session_factory() as sess:
            yield sess

    async def override_get_conversation_service() -> ConversationService:
        return svc

    test_settings = Settings()
    app = create_app(test_settings)

    # Wire required app.state items.
    app.state.jwks_fetcher = MagicMock()
    app.state.conversation_service = svc

    # Override FastAPI dependencies.
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_conversation_service] = override_get_conversation_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, svc


# ---------------------------------------------------------------------------
# Helper: create a conversation directly in the DB
# ---------------------------------------------------------------------------


async def create_conv(
    session: AsyncSession,
    user_id: uuid.UUID,
    title: str | None = None,
    foundry_conv_id: str | None = None,
) -> Conversation:
    conv = Conversation(
        id=uuid.uuid4(),
        user_id=user_id,
        title=title,
        foundry_conversation_id=foundry_conv_id,
    )
    session.add(conv)
    await session.flush()
    return conv


async def create_message(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
) -> Message:
    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role=role,
        content=content,
    )
    session.add(msg)
    await session.flush()
    return msg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_conversations_returns_user_only(
    session_factory,
    user_a: User,
    user_b: User,
    session: AsyncSession,
):
    """User A must not see User B's conversations."""
    conv_a = await create_conv(session, user_a.id, title="A's conv")
    conv_b = await create_conv(session, user_b.id, title="B's conv")
    await session.commit()

    async for client, _svc in make_client(session_factory, user_a):
        response = await client.get("/conversations")
        assert response.status_code == 200
        data = response.json()
        ids = [c["id"] for c in data]
        assert str(conv_a.id) in ids
        assert str(conv_b.id) not in ids


@pytest.mark.asyncio
async def test_list_conversations_ordered_by_created_at_desc(
    session_factory,
    user_a: User,
    session: AsyncSession,
):
    """Conversations must be ordered newest-first."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    conv1 = await create_conv(session, user_a.id, title="First")
    conv1.created_at = now - timedelta(hours=1)
    conv2 = await create_conv(session, user_a.id, title="Second")
    conv2.created_at = now
    await session.commit()

    async for client, _svc in make_client(session_factory, user_a):
        response = await client.get("/conversations")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == str(conv2.id)
        assert data[1]["id"] == str(conv1.id)


@pytest.mark.asyncio
async def test_list_conversations_respects_limit(
    session_factory,
    user_a: User,
    session: AsyncSession,
):
    """The ?limit query param must be respected."""
    for i in range(5):
        conv = await create_conv(session, user_a.id, title=f"Conv {i}")
        session.add(conv)
    await session.commit()

    async for client, _svc in make_client(session_factory, user_a):
        response = await client.get("/conversations?limit=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3


@pytest.mark.asyncio
async def test_get_conversation_returns_detail_with_messages(
    session_factory,
    user_a: User,
    session: AsyncSession,
):
    """GET /conversations/{id} must include all messages."""
    conv = await create_conv(session, user_a.id, title="My Chat")
    await create_message(session, conv.id, "user", "Hello")
    await create_message(session, conv.id, "assistant", "Hi there!")
    await session.commit()

    async for client, _svc in make_client(session_factory, user_a):
        response = await client.get(f"/conversations/{conv.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(conv.id)
        assert data["title"] == "My Chat"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["content"] == "Hello"
        assert data["messages"][1]["content"] == "Hi there!"


@pytest.mark.asyncio
async def test_get_conversation_404_for_other_user_conversation(
    session_factory,
    user_a: User,
    user_b: User,
    session: AsyncSession,
):
    """Accessing another user's conversation must return 404."""
    conv = await create_conv(session, user_b.id, title="B's private")
    await session.commit()

    async for client, _svc in make_client(session_factory, user_a):
        response = await client.get(f"/conversations/{conv.id}")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_conversation_404_for_nonexistent_id(
    session_factory,
    user_a: User,
):
    """GET /conversations/{random-uuid} must return 404."""
    async for client, _svc in make_client(session_factory, user_a):
        response = await client.get(f"/conversations/{uuid.uuid4()}")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_conversation_returns_empty(
    session_factory,
    user_a: User,
):
    """POST /conversations must return a detail object with an empty messages list."""
    async for client, _svc in make_client(session_factory, user_a):
        response = await client.post("/conversations", json={})
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["messages"] == []
        assert data["title"] is None


@pytest.mark.asyncio
async def test_create_conversation_with_title(
    session_factory,
    user_a: User,
):
    """POST /conversations with a title must store it."""
    async for client, _svc in make_client(session_factory, user_a):
        response = await client.post("/conversations", json={"title": "My Chat"})
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "My Chat"


@pytest.mark.asyncio
async def test_patch_conversation_updates_title(
    session_factory,
    user_a: User,
    session: AsyncSession,
):
    """PATCH /conversations/{id} must update the title."""
    conv = await create_conv(session, user_a.id, title="Old Title")
    await session.commit()

    async for client, _svc in make_client(session_factory, user_a):
        response = await client.patch(
            f"/conversations/{conv.id}",
            json={"title": "New Title"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Title"


@pytest.mark.asyncio
async def test_patch_conversation_404_for_other_user(
    session_factory,
    user_a: User,
    user_b: User,
    session: AsyncSession,
):
    """PATCH on another user's conversation must return 404."""
    conv = await create_conv(session, user_b.id, title="Private")
    await session.commit()

    async for client, _svc in make_client(session_factory, user_a):
        response = await client.patch(
            f"/conversations/{conv.id}",
            json={"title": "Hacked"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation_returns_204(
    session_factory,
    user_a: User,
    session: AsyncSession,
):
    """DELETE /conversations/{id} must return 204."""
    conv = await create_conv(session, user_a.id, title="To Delete")
    await session.commit()

    async for client, _svc in make_client(session_factory, user_a):
        response = await client.delete(f"/conversations/{conv.id}")
        assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_conversation_cascades_messages(
    session_factory,
    user_a: User,
    session: AsyncSession,
):
    """Deleting a conversation must CASCADE-delete its messages."""
    conv = await create_conv(session, user_a.id)
    msg = await create_message(session, conv.id, "user", "Will be deleted")
    await session.commit()

    async for client, _svc in make_client(session_factory, user_a):
        response = await client.delete(f"/conversations/{conv.id}")
        assert response.status_code == 204

    # Verify message is gone (FK cascade).
    from sqlalchemy import select

    row = await session.execute(select(Message).where(Message.id == msg.id))
    assert row.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_conversation_404_for_other_user(
    session_factory,
    user_a: User,
    user_b: User,
    session: AsyncSession,
):
    """DELETE on another user's conversation must return 404."""
    conv = await create_conv(session, user_b.id, title="Private")
    await session.commit()

    async for client, _svc in make_client(session_factory, user_a):
        response = await client.delete(f"/conversations/{conv.id}")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_all_endpoints_require_auth(session_factory, user_a: User):
    """All endpoints must return 401 when no Authorization header is present."""
    from fastapi import HTTPException

    from app.api.auth.deps import get_conversation_service, get_current_user
    from app.db.session import get_session
    from app.main import create_app
    from app.settings import Settings

    svc = ConversationService(session_factory=session_factory)

    async def fail_auth() -> User:
        raise HTTPException(status_code=401, detail="not authenticated")

    async def override_get_session() -> AsyncSession:
        async with session_factory() as sess:
            yield sess

    async def override_get_conversation_service() -> ConversationService:
        return svc

    test_settings = Settings()
    app = create_app(test_settings)
    app.state.jwks_fetcher = MagicMock()
    app.state.conversation_service = svc
    app.dependency_overrides[get_current_user] = fail_auth
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_conversation_service] = override_get_conversation_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for method, url in [
            ("get", "/conversations"),
            ("post", "/conversations"),
            ("get", f"/conversations/{uuid.uuid4()}"),
            ("patch", f"/conversations/{uuid.uuid4()}"),
            ("delete", f"/conversations/{uuid.uuid4()}"),
        ]:
            response = await ac.request(method, url, json={})
            assert response.status_code == 401, f"{method.upper()} {url} should return 401"
