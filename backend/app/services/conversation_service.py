"""Conversation service — owns the lifecycle of Conversation rows.

Provides get-or-create, session linking to Foundry, title management,
and per-user conversation listing.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.conversation import Conversation

if TYPE_CHECKING:
    from app.domain.user import User


class ConversationNotFoundError(ValueError):
    """Raised when a conversation id is provided but no matching row exists.

    The error message uses neutral professional Spanish per the project
    convention for user-facing strings in error paths.
    """

    def __init__(self, conversation_id: uuid.UUID) -> None:
        self.conversation_id = conversation_id
        super().__init__(f"No se encontró la conversación con id={conversation_id}.")


class ConversationService:
    """Service for managing conversation rows.

    Parameters
    ----------
    session_factory
        A callable that yields an :class:`AsyncSession` (e.g. the
        ``async_sessionmaker`` from :mod:`app.db.session`).
    """

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    ) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_or_create(
        self,
        *,
        user: User,
        conversation_id: uuid.UUID | None,
        session: AsyncSession | None = None,
    ) -> tuple[Conversation, bool]:
        """Fetch an existing conversation or create a new one.

        Parameters
        ----------
        user
            The authenticated user who owns the conversation.
        conversation_id
            ``None`` → always create a new conversation.
            A UUID → look it up scoped to ``user`` first.
        session
            Optional; if provided the service uses this session instead of
            opening a new one (useful in tests to keep everything in one tx).

        Returns
        -------
        tuple[Conversation, bool]
            ``(conversation, created)`` where ``created`` is ``True`` when
            a new row was inserted.

        Raises
        ------
        ConversationNotFoundError
            When ``conversation_id`` is provided but the row either does not
            exist or belongs to a different user.
        """
        if session is not None:
            return await self._get_or_create_with_session(
                session=session, user=user, conversation_id=conversation_id
            )
        async with self._session_factory() as session:
            return await self._get_or_create_with_session(
                session=session, user=user, conversation_id=conversation_id
            )

    async def _get_or_create_with_session(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID | None,
    ) -> tuple[Conversation, bool]:
        """Internal implementation shared by both session paths."""
        if conversation_id is not None:
            row = await session.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user.id,
                )
            )
            conv = row.scalar_one_or_none()
            if conv is None:
                raise ConversationNotFoundError(conversation_id)
            return conv, False

        conv = Conversation(user_id=user.id, title=None)
        session.add(conv)
        await session.flush()
        await session.commit()
        await session.refresh(conv)
        return conv, True

    async def link_foundry_session(
        self,
        conversation: Conversation,
        foundry_conversation_id: str,
        session: AsyncSession | None = None,
    ) -> Conversation:
        """Record the Foundry session id on a conversation row.

        This is idempotent: if the conversation already has the same
        ``foundry_conversation_id`` the row is not updated.

        Parameters
        ----------
        conversation
            The conversation row to update.
        foundry_conversation_id
            The session id returned by ``FoundryAgent.create_session()``.
        session
            Optional; uses an internal session if not provided.

        Returns
        -------
        Conversation
            The updated conversation row.
        """
        if session is not None:
            return await self._link_with_session(
                conversation=conversation,
                foundry_conversation_id=foundry_conversation_id,
                session=session,
            )
        async with self._session_factory() as session:
            return await self._link_with_session(
                conversation=conversation,
                foundry_conversation_id=foundry_conversation_id,
                session=session,
            )

    async def _link_with_session(
        self,
        conversation: Conversation,
        foundry_conversation_id: str,
        session: AsyncSession,
    ) -> Conversation:
        """Internal implementation shared by both session paths."""
        row = await session.execute(select(Conversation).where(Conversation.id == conversation.id))
        conv = row.scalar_one()

        if conv.foundry_conversation_id == foundry_conversation_id:
            return conv

        conv.foundry_conversation_id = foundry_conversation_id
        await session.flush()
        await session.commit()
        return conv

    async def list_for_user(
        self,
        *,
        user: User,
        limit: int = 50,
        session: AsyncSession | None = None,
    ) -> list[Conversation]:
        """Return the most recent conversations for a user.

        Parameters
        ----------
        user
            The conversation owner.
        limit
            Maximum number of rows to return (default 50).
        session
            Optional; uses an internal session if not provided.

        Returns
        -------
        list[Conversation]
            Conversations ordered by ``created_at`` descending.
        """
        if session is not None:
            return await self._list_with_session(user=user, limit=limit, session=session)
        async with self._session_factory() as session:
            return await self._list_with_session(user=user, limit=limit, session=session)

    async def _list_with_session(
        self,
        user: User,
        limit: int,
        session: AsyncSession,
    ) -> list[Conversation]:
        """Internal implementation shared by both session paths."""
        row = await session.execute(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        return list(row.scalars().all())

    async def set_title(
        self,
        conversation: Conversation,
        title: str,
        session: AsyncSession | None = None,
    ) -> Conversation:
        """Set (or clear) the title of a conversation.

        Parameters
        ----------
        conversation
            The conversation row to update.
        title
            The new title. Empty string clears the title.
            Titles longer than 255 characters are silently truncated.
        session
            Optional; uses an internal session if not provided.

        Returns
        -------
        Conversation
            The updated conversation row.
        """
        if session is not None:
            return await self._set_title_with_session(
                conversation=conversation, title=title, session=session
            )
        async with self._session_factory() as session:
            return await self._set_title_with_session(
                conversation=conversation, title=title, session=session
            )

    async def _set_title_with_session(
        self,
        conversation: Conversation,
        title: str,
        session: AsyncSession,
    ) -> Conversation:
        """Internal implementation shared by both session paths."""
        trimmed = title[:255] if len(title) > 255 else title
        row = await session.execute(select(Conversation).where(Conversation.id == conversation.id))
        conv = row.scalar_one()
        conv.title = trimmed if trimmed else None
        await session.flush()
        await session.commit()
        return conv
