"""Foundry streaming service.

This is the only module that imports ``agent_framework`` streaming primitives.
It wraps ``agent.run(stream=True, session=session)`` and exposes a simple
async-iterator interface that yields :class:`StreamEvent` objects.

Resolved streaming API (per OpenSpec cached preference):
- ``stream = agent.run(input, stream=True, session=session)`` → ``ResponseStream`` (NOT awaitable)
- ``async for update in stream:`` yields ``AgentResponseUpdate`` with ``.text``
- ``await stream.get_final_response()`` → ``AgentResponse`` with ``.text``
- ``agent.create_session()`` / ``agent.get_session(service_session_id="<id>")`` for sessions
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from agent_framework.foundry import FoundryAgent

from app.services.stream_events import StreamEvent
from app.services.stream_events import delta as make_delta
from app.services.stream_events import error as make_error
from app.services.stream_events import final as make_final

if TYPE_CHECKING:
    from app.services.foundry import FoundryClient

logger = logging.getLogger(__name__)


class FoundryStreamService:
    """Wraps a :class:`FoundryClient` for streaming chat turns.

    Unlike the single-shot :meth:`FoundryClient.invoke`, this class
    iterates the ``ResponseStream`` and yields text deltas as they arrive.
    """

    def __init__(self, foundry_client: FoundryClient) -> None:
        """Initialise the service with a shared :class:`FoundryClient`.

        Parameters
        ----------
        foundry_client
            The shared Foundry client (already opened in the FastAPI lifespan).
        """
        self._client = foundry_client

    # ------------------------------------------------------------------
    # Public streaming API
    # ------------------------------------------------------------------

    async def stream_chat(
        self,
        *,
        user_message: str,
        service_session_id: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a chat turn and yield structured events.

        Parameters
        ----------
        user_message
            The user's message to send to the agent.
        service_session_id
            ``None`` → create a new Foundry session.
            A value → resume that existing Foundry session.
        agent_name
            Override the agent name for this call.
        agent_version
            Override the agent version for this call.

        Yields
        ------
        StreamDelta
            For each non-empty ``update.text`` received from the agent.
        StreamFinal
            After the stream completes, with the aggregated text and the
            Foundry ``service_session_id``.
        StreamError
            If any exception occurs; the caller handles the error code.
        """
        try:
            agent, session = await self._build_agent_and_session(
                agent_name=agent_name,
                agent_version=agent_version,
                service_session_id=service_session_id,
            )

            stream = agent.run(
                input=user_message,
                stream=True,
                session=session,
            )

            async for update in stream:
                if update.text:
                    yield make_delta(update.text)

            final_response = await stream.get_final_response()
            yield make_final(
                text=final_response.text,
                service_session_id=session.service_session_id,
            )

        except Exception as exc:  # noqa: BLE001
            logger.warning("foundry_stream_error error=%s", str(exc))
            yield make_error(str(exc))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _build_agent_and_session(
        self,
        agent_name: str | None,
        agent_version: str | None,
        service_session_id: str | None,
    ) -> tuple[FoundryAgent, object]:
        """Resolve the agent and the session, creating one if needed."""
        client = await self._client._ensure_client()  # noqa: SLF001

        agent = FoundryAgent(
            project_client=client,
            agent_name=agent_name or self._client.agent_name,
            agent_version=agent_version or self._client.agent_version,
        )

        if service_session_id is None:
            session = agent.create_session()
        else:
            session = agent.get_session(service_session_id=service_session_id)

        return agent, session
