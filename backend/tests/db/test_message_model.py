"""Roundtrip tests for the Message model."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Conversation, Message, User


@pytest.mark.asyncio
async def test_message_create_and_fetch(session: AsyncSession) -> None:
    """A message linked to a conversation can be fetched by its UUID."""
    user = User(entraid_oid="msg-user-oid")
    session.add(user)
    await session.commit()

    conv = Conversation(user_id=user.id)
    session.add(conv)
    await session.commit()

    msg = Message(
        conversation_id=conv.id,
        role="user",
        content="Hello, I need help.",
    )
    session.add(msg)
    await session.commit()

    fetched = await session.get(Message, msg.id)
    assert fetched is not None
    assert fetched.id == msg.id
    assert fetched.conversation_id == conv.id
    assert fetched.role == "user"
    assert fetched.content == "Hello, I need help."
    assert fetched.created_at is not None


@pytest.mark.asyncio
async def test_messages_ordered_by_created_at(session: AsyncSession) -> None:
    """Messages are returned in chronological order by created_at."""
    user = User(entraid_oid="order-user-oid")
    session.add(user)
    await session.commit()

    conv = Conversation(user_id=user.id)
    session.add(conv)
    await session.commit()

    msg1 = Message(conversation_id=conv.id, role="user", content="First")
    msg2 = Message(conversation_id=conv.id, role="assistant", content="Second")
    msg3 = Message(conversation_id=conv.id, role="user", content="Third")
    session.add_all([msg1, msg2, msg3])
    await session.commit()

    result = await session.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
    )
    messages = result.scalars().all()
    assert len(messages) == 3
    assert messages[0].content == "First"
    assert messages[1].content == "Second"
    assert messages[2].content == "Third"


@pytest.mark.asyncio
async def test_message_cascade_delete_on_conversation(session: AsyncSession) -> None:
    """Deleting a conversation removes all its messages."""
    user = User(entraid_oid="cascade-conv-user")
    session.add(user)
    await session.commit()

    conv = Conversation(user_id=user.id)
    session.add(conv)
    await session.commit()

    session.add_all(
        [
            Message(conversation_id=conv.id, role="user", content="One"),
            Message(conversation_id=conv.id, role="assistant", content="Two"),
        ]
    )
    await session.commit()

    await session.delete(conv)
    await session.commit()

    result = await session.execute(select(Message).where(Message.conversation_id == conv.id))
    assert result.scalars().all() == []
