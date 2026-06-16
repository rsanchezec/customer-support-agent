"""Foundry streaming service.

Pattern: canonical SDK 1.8.0+ pattern (same as example/002-batman-agent-streaming.py).
Use `agent.run(input, stream=True, session=session)` to get a real ResponseStream.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from agent_framework.foundry import FoundryAgent
from azure.ai.projects.aio import AIProjectClient

from app.services.stream_events import StreamEvent
from app.services.stream_events import delta as make_delta
from app.services.stream_events import error as make_error
from app.services.stream_events import final as make_final

if TYPE_CHECKING:
    from app.services.foundry import FoundryClient

logger = logging.getLogger(__name__)


class FoundryStreamService:
    """Wrap a Foundry client and expose chat turns as structured events."""

    def __init__(self, foundry_client: FoundryClient) -> None:
        self._client = foundry_client
        self._agent: FoundryAgent | None = None

    async def _get_agent(self) -> FoundryAgent:
        """Lazy-build the FoundryAgent on first use (cached for the process)."""
        if self._agent is not None:
            return self._agent
        async with AIProjectClient(
            endpoint=self._client.endpoint,
            credential=self._client._credential,  # noqa: SLF001
        ) as project_client:
            agent_name = self._client.agent_name
            agent_version = self._client.agent_version
            if agent_version:
                resolved = await project_client.agents.get_version(
                    agent_name=agent_name, agent_version=agent_version,
                )
            else:
                versions = []
                async for v in project_client.agents.list_versions(agent_name=agent_name):
                    versions.append(v)
                if not versions:
                    raise RuntimeError(f"No versions found for agent '{agent_name}'")
                resolved = max(versions, key=lambda v: int(v.version) if v.version.isdigit() else 0)
            self._agent = FoundryAgent(
                project_client=project_client,
                agent_name=resolved.name,
                agent_version=resolved.version,
            )
        return self._agent

    async def stream_chat(
        self,
        *,
        user_message: str,
        service_session_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream one chat turn using the canonical SDK 1.8.0+ pattern.

        Yields: StreamDelta per chunk, StreamFinal at the end, or StreamError on failure.
        """
        try:
            agent = await self._get_agent()
            if service_session_id:
                session = agent.get_session(service_session_id=service_session_id)
            else:
                session = agent.create_session()
            stream = agent.run(user_message, stream=True, session=session)
            accumulated = ""
            async for update in stream:
                text = getattr(update, "text", "")
                if text:
                    accumulated += text
                    yield make_delta(text)
            try:
                final = await stream.get_final_response()
                final_text = getattr(final, "text", "") or accumulated
            except Exception:
                final_text = accumulated
            if not final_text:
                yield make_error("El agente respondio vacio.")
                return
            if not accumulated:
                yield make_delta(final_text)
            yield make_final(text=final_text, service_session_id=service_session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("foundry_stream_error error=%s", str(exc), exc_info=True)
            yield make_error(str(exc))
