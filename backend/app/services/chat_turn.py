"""Chat turn orchestrator.

Coordinates the full lifecycle of one chat turn:
1. Persist the user message immediately (before the Foundry call).
2. Stream deltas from Foundry while yielding events to the caller.
3. Persist the assistant message once the stream finishes.
4. Link the conversation to the Foundry session id (on first turn).

The WS endpoint (:mod:`app.api.ws.chat`) is the only caller.  It iterates
the returned async iterator, serialises each event, and sends it over the
WebSocket.  This service is the **single source of truth for persistence**;
the WS endpoint never touches the database directly.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.conversation import Conversation
from app.domain.message import Message
from app.services.stream_events import StreamEvent, StreamFinal

if TYPE_CHECKING:
    from app.domain.user import User
    from app.services.foundry import FoundryClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatTurnResult:
    """Returned after a complete chat turn (after the stream finishes)."""

    assistant_text: str
    conversation_id: uuid.UUID


class ChatTurnService:
    """Orchestrates one user → assistant chat turn.

    Parameters
    ----------
    session
        An open :class:`AsyncSession` (FastAPI's ``get_session`` dependency).
    foundry_client
        The shared :class:`FoundryClient` opened in the FastAPI lifespan.
    conversation
        The active :class:`Conversation` row (already resolved by the caller
        via :class:`ConversationService`).
    """

    def __init__(
        self,
        session: AsyncSession,
        foundry_client: FoundryClient,
        conversation: Conversation,
    ) -> None:
        self._session = session
        self._foundry_client = foundry_client
        self._conversation = conversation

    async def execute(
        self,
        *,
        user: User,
        user_message: str,
    ) -> tuple[AsyncIterator[StreamEvent], ChatTurnResult]:
        """Execute a full chat turn.

        Parameters
        ----------
        user
            The authenticated end-user (from the JWT dependency).
        user_message
            The raw text sent by the client.

        Returns
        -------
        tuple[AsyncIterator[StreamEvent], ChatTurnResult]
            An async iterator of stream events (yielded as the turn progresses)
            and the final result containing the assistant's text and the
            conversation id.

        Persistence contract
        --------------------
        - User message is persisted **before** ``stream_chat`` is called.
        - Assistant message is persisted **after** the ``StreamFinal`` event
          is yielded (i.e. after the stream finishes).
        - If an error occurs, no assistant row is inserted.
        """
        conv = self._conversation

        # ------------------------------------------------------------------
        # 1. Persist the user message immediately
        # ------------------------------------------------------------------
        user_msg = Message(
            conversation_id=conv.id,
            role="user",
            content=user_message,
        )
        self._session.add(user_msg)
        await self._session.flush()
        # Commit so the row is visible even if the stream crashes.
        await self._session.commit()

        # ------------------------------------------------------------------
        # 2. Build the Foundry streaming service
        # ------------------------------------------------------------------
        from app.services.foundry_stream import FoundryStreamService

        stream_svc = FoundryStreamService(self._foundry_client)

        async def turn_events() -> AsyncIterator[StreamEvent]:
            async for event in stream_svc.stream_chat(
                user_message=user_message,
                service_session_id=conv.foundry_conversation_id,
            ):
                # ------------------------------------------------------------------
                # 3. After the StreamFinal event, link the Foundry session id
                # ------------------------------------------------------------------
                if isinstance(event, StreamFinal):
                    if event.service_session_id is not None:
                        await self._link_foundry_session(conv, event.service_session_id)
                yield event

        return turn_events(), ChatTurnResult(
            assistant_text="",  # filled in by caller after streaming
            conversation_id=conv.id,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _link_foundry_session(
        self,
        conversation: Conversation,
        foundry_conversation_id: str,
    ) -> None:
        """Record the Foundry session id on the conversation row (first turn).

        Idempotent: if the conversation already has this foundry_conversation_id
        the UPDATE is skipped.
        """
        # Only link if not already set.
        if conversation.foundry_conversation_id is not None:
            return
        conversation.foundry_conversation_id = foundry_conversation_id
        await self._session.flush()
        await self._session.commit()

    # ------------------------------------------------------------------
    # Called by the WS endpoint after the StreamFinal event is received
    # ------------------------------------------------------------------

    async def persist_assistant_message(
        self,
        conversation_id: uuid.UUID,
        assistant_text: str,
    ) -> Message:
        """Insert one assistant :class:`Message` row after the stream completes.

        Called by the WS endpoint **after** the ``StreamFinal`` event so that
        the assistant row is only persisted on success.
        """
        msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_text,
        )
        self._session.add(msg)
        await self._session.flush()
        await self._session.commit()
        return msg
