"""REST router for conversation history.

GET  /conversations              — list all for the current user
POST /conversations              — create a new empty conversation
GET  /conversations/{id}         — fetch one conversation with messages
PATCH /conversations/{id}        — update the title
DELETE /conversations/{id}       — delete the conversation (cascade)
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.deps import get_conversation_service, get_current_user
from app.api.rest.schemas import (
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)
from app.db.session import get_session
from app.domain.conversation import Conversation
from app.domain.message import Message
from app.domain.user import User
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_conv_or_404(
    conversation_id: UUID,
    user: User,
    session: AsyncSession,
    svc: ConversationService,
) -> Conversation:
    """Look up a conversation owned by the current user or raise 404."""
    row = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )
    conv = row.scalar_one_or_none()
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="conversation not found",
        )
    return conv


async def _get_messages(session: AsyncSession, conversation_id: UUID) -> list[Message]:
    """Return all messages for a conversation in chronological order."""
    row = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list(row.scalars().all())


async def _get_message_count(session: AsyncSession, conversation_id: UUID) -> int:
    """Return the number of messages in a conversation."""
    from sqlalchemy import func

    row = await session.execute(
        select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    )
    return row.scalar_one()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[ConversationOut],
    summary="List conversations",
    description="Return all conversations owned by the authenticated user, newest first.",
)
async def list_conversations(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    svc: Annotated[ConversationService, Depends(get_conversation_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ConversationOut]:
    conversations = await svc.list_for_user(user=user, limit=limit, session=session)
    result: list[ConversationOut] = []
    for conv in conversations:
        count = await _get_message_count(session, conv.id)
        result.append(
            ConversationOut(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                message_count=count,
            )
        )
    return result


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetailOut,
    summary="Get conversation detail",
    description="Return a single conversation with all its messages.",
)
async def get_conversation(
    conversation_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    svc: Annotated[ConversationService, Depends(get_conversation_service)],
) -> ConversationDetailOut:
    conv = await _get_conv_or_404(conversation_id, user, session, svc)
    messages = await _get_messages(session, conversation_id)
    return ConversationDetailOut(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        foundry_conversation_id=conv.foundry_conversation_id or "",
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,  # type: ignore[arg-type]  # Literal enforced by model
                content=m.content,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ConversationDetailOut,
    summary="Create conversation",
    description="Create a new empty conversation. The first message will be sent via WebSocket.",
)
async def create_conversation(
    body: ConversationCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    svc: Annotated[ConversationService, Depends(get_conversation_service)],
) -> ConversationDetailOut:
    conv, _created = await svc.get_or_create(
        user=user,
        conversation_id=None,
        session=session,
    )
    if body.title is not None:
        conv = await svc.set_title(conv, body.title, session=session)
    return ConversationDetailOut(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        foundry_conversation_id=conv.foundry_conversation_id or "",
        messages=[],
    )


@router.patch(
    "/{conversation_id}",
    response_model=ConversationDetailOut,
    summary="Update conversation title",
)
async def patch_conversation(
    conversation_id: UUID,
    body: ConversationUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    svc: Annotated[ConversationService, Depends(get_conversation_service)],
) -> ConversationDetailOut:
    conv = await _get_conv_or_404(conversation_id, user, session, svc)
    conv = await svc.set_title(conv, body.title, session=session)
    messages = await _get_messages(session, conversation_id)
    return ConversationDetailOut(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        foundry_conversation_id=conv.foundry_conversation_id or "",
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,  # type: ignore[arg-type]
                content=m.content,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete conversation",
    description="Delete a conversation and all its messages (CASCADE).",
)
async def delete_conversation(
    conversation_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    svc: Annotated[ConversationService, Depends(get_conversation_service)],
) -> None:
    conv = await _get_conv_or_404(conversation_id, user, session, svc)
    await session.delete(conv)
    await session.commit()
