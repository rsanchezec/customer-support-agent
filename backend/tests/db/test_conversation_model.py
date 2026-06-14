"""Roundtrip tests for the Conversation model."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Conversation, User


@pytest.mark.asyncio
async def test_conversation_create_and_fetch_by_id(session: AsyncSession) -> None:
    """A conversation linked to a user can be fetched by its UUID."""
    user = User(entraid_oid="u1-oid")
    session.add(user)
    await session.commit()

    conv = Conversation(user_id=user.id, title="Support Chat")
    session.add(conv)
    await session.commit()

    fetched = await session.get(Conversation, conv.id)
    assert fetched is not None
    assert fetched.id == conv.id
    assert fetched.user_id == user.id
    assert fetched.title == "Support Chat"
    assert fetched.foundry_conversation_id is None
    assert fetched.created_at is not None


@pytest.mark.asyncio
async def test_conversation_cascade_delete_on_user(session: AsyncSession) -> None:
    """Deleting a user removes all their conversations."""
    user = User(entraid_oid="cascade-user")
    session.add(user)
    await session.commit()

    conv1 = Conversation(user_id=user.id, title="Chat 1")
    conv2 = Conversation(user_id=user.id, title="Chat 2")
    session.add_all([conv1, conv2])
    await session.commit()

    await session.delete(user)
    await session.commit()

    result = await session.execute(select(Conversation).where(Conversation.user_id == user.id))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_conversation_foundry_id_unique_per_user(session: AsyncSession) -> None:
    """The foundry_conversation_id column is unique per conversation."""
    user = User(entraid_oid="unique-foundry-user")
    session.add(user)
    await session.commit()

    conv1 = Conversation(user_id=user.id, foundry_conversation_id="fc-1")
    conv2 = Conversation(user_id=user.id, foundry_conversation_id="fc-1")
    session.add(conv1)
    await session.commit()

    session.add(conv2)
    with pytest.raises(Exception):
        await session.flush()
