"""Foundry streaming service.

This module is the boundary between the FastAPI app and Agent Framework. It
uses the streaming API exposed by the installed SDK:

- ``stream = agent.run(input, stream=True)`` returns a ``ResponseStream``.
- ``async for update in stream`` yields updates with a ``.text`` field.
- ``await stream.get_final_response()`` returns the final response.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from agent_framework.foundry import FoundryAgent
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import AgentVersionDetails

from app.services.stream_events import StreamEvent
from app.services.stream_events import delta as make_delta
from app.services.stream_events import error as make_error
from app.services.stream_events import final as make_final

if TYPE_CHECKING:
    from app.services.foundry import FoundryClient

logger = logging.getLogger(__name__)

STREAM_STEP_TIMEOUT_SECONDS = 30


class FoundryStreamService:
    """Wrap a Foundry client and expose chat turns as structured events."""

    def __init__(self, foundry_client: FoundryClient) -> None:
        """Initialize the service with the shared app Foundry client."""
        self._client = foundry_client
        self._last_stream: object | None = None

    async def stream_chat(
        self,
        *,
        user_message: str,
        service_session_id: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream one chat turn and yield deltas, final, or error events."""
        try:
            logger.warning(
                "[CHAT DEBUG] foundry_stream_start has_service_session=%s timeout_seconds=%s",
                service_session_id is not None,
                STREAM_STEP_TIMEOUT_SECONDS,
            )
            logger.warning(
                "[CHAT DEBUG] foundry_client_open endpoint=%s agent_name=%s agent_version=%s",
                self._client.endpoint,
                agent_name or self._client.agent_name,
                agent_version or self._client.agent_version or "<latest>",
            )
            async with AIProjectClient(
                endpoint=self._client.endpoint,
                credential=self._client._credential,  # noqa: SLF001
            ) as project_client:
                logger.warning("[CHAT DEBUG] foundry_project_client_ready")
                resolved = await asyncio.wait_for(
                    self._resolve_agent(
                        project_client=project_client,
                        agent_name=agent_name or self._client.agent_name,
                        agent_version=agent_version or self._client.agent_version,
                    ),
                    timeout=STREAM_STEP_TIMEOUT_SECONDS,
                )

                logger.warning(
                    "[CHAT DEBUG] foundry_agent_resolved agent_name=%s agent_version=%s",
                    resolved.name,
                    resolved.version,
                )

                agent = FoundryAgent(
                    project_client=project_client,
                    agent_name=resolved.name,
                    agent_version=resolved.version,
                )

                try:
                    full_text = ""
                    logger.warning("[CHAT DEBUG] foundry_stream_call_start")
                    async for text in self._run_stream(agent, user_message):
                        full_text += text
                        yield make_delta(text)

                    logger.warning(
                        "[CHAT DEBUG] foundry_stream_call_done accumulated_len=%s",
                        len(full_text),
                    )
                    final_text = await self._get_final_text(fallback=full_text)
                    if final_text and not full_text:
                        logger.warning(
                            "[CHAT DEBUG] foundry_final_without_deltas len=%s",
                            len(final_text),
                        )
                        async for text in self._fake_stream(final_text):
                            yield make_delta(text)

                    if final_text:
                        logger.warning("[CHAT DEBUG] foundry_final len=%s", len(final_text))
                        yield make_final(
                            text=final_text,
                            service_session_id=service_session_id,
                        )
                        return
                    logger.warning("[CHAT DEBUG] foundry_stream_empty falling_back_to_run")
                except (TypeError, AttributeError) as exc:
                    logger.warning(
                        "[CHAT DEBUG] foundry_stream_unavailable falling_back_to_run error=%s",
                        str(exc),
                    )

                logger.warning("[CHAT DEBUG] foundry_run_fallback_start")
                response_text = await self._run_once(agent, user_message)
                async for text in self._fake_stream(response_text):
                    yield make_delta(text)
                logger.warning("[CHAT DEBUG] foundry_run_fallback_done len=%s", len(response_text))
                yield make_final(text=response_text, service_session_id=service_session_id)

        except TimeoutError:
            logger.warning(
                "[CHAT DEBUG] foundry_timeout timeout_seconds=%s",
                STREAM_STEP_TIMEOUT_SECONDS,
            )
            yield make_error("El agente tardo demasiado en responder. Intenta de nuevo.")

        except Exception as exc:  # noqa: BLE001
            logger.warning("[CHAT DEBUG] foundry_error error=%s", str(exc), exc_info=True)
            yield make_error(str(exc))

    async def _resolve_agent(
        self,
        project_client: AIProjectClient,
        agent_name: str | None,
        agent_version: str | None,
    ) -> AgentVersionDetails:
        """Resolve the configured agent version, or latest if no version is set."""
        if agent_version:
            return await project_client.agents.get_version(
                agent_name=agent_name,
                agent_version=agent_version,
            )

        versions: list[AgentVersionDetails] = []
        async for version in project_client.agents.list_versions(agent_name=agent_name):
            versions.append(version)

        if not versions:
            raise RuntimeError(
                f"No versions found for agent '{agent_name}'. Publish a version first."
            )

        def version_key(version: AgentVersionDetails) -> tuple[int, int | str]:
            try:
                return (0, int(version.version))
            except (TypeError, ValueError):
                return (1, str(version.version))

        return max(versions, key=version_key)

    async def _run_stream(self, agent: FoundryAgent, user_message: str) -> AsyncIterator[str]:
        """Yield text chunks from ``FoundryAgent.run(..., stream=True)``."""
        logger.warning(
            "[CHAT DEBUG] foundry_run_stream_invoking message_len=%s",
            len(user_message),
        )
        stream = agent.run(user_message, stream=True)
        self._last_stream = stream
        logger.warning(
            "[CHAT DEBUG] foundry_run_stream_returned stream_type=%s",
            type(stream).__name__,
        )
        stream_iter = stream.__aiter__()
        chunk_index = 0
        while True:
            try:
                logger.warning(
                    "[CHAT DEBUG] foundry_wait_next_chunk index=%s timeout_seconds=%s",
                    chunk_index,
                    STREAM_STEP_TIMEOUT_SECONDS,
                )
                update = await asyncio.wait_for(
                    stream_iter.__anext__(),
                    timeout=STREAM_STEP_TIMEOUT_SECONDS,
                )
            except StopAsyncIteration:
                break

            text = getattr(update, "text", "")
            if text:
                logger.warning(
                    "[CHAT DEBUG] foundry_chunk index=%s len=%s update_type=%s",
                    chunk_index,
                    len(text),
                    type(update).__name__,
                )
                yield text
            else:
                logger.warning(
                    "[CHAT DEBUG] foundry_empty_chunk index=%s update_type=%s",
                    chunk_index,
                    type(update).__name__,
                )
            chunk_index += 1

    async def _get_final_text(self, *, fallback: str) -> str:
        """Read the final response text from the latest ResponseStream."""
        stream = self._last_stream
        if stream is None:
            return fallback

        get_final_response = getattr(stream, "get_final_response", None)
        if not callable(get_final_response):
            logger.warning("[CHAT DEBUG] foundry_final_unavailable")
            return fallback

        logger.warning(
            "[CHAT DEBUG] foundry_final_wait timeout_seconds=%s fallback_len=%s",
            STREAM_STEP_TIMEOUT_SECONDS,
            len(fallback),
        )
        final = await asyncio.wait_for(
            get_final_response(),
            timeout=STREAM_STEP_TIMEOUT_SECONDS,
        )
        logger.warning(
            "[CHAT DEBUG] foundry_final_received final_type=%s len=%s",
            type(final).__name__,
            len(getattr(final, "text", "") or ""),
        )
        return getattr(final, "text", "") or fallback

    async def _run_once(self, agent: FoundryAgent, user_message: str) -> str:
        """Call ``FoundryAgent.run()`` and return the final text."""
        logger.warning(
            "[CHAT DEBUG] foundry_run_once_wait timeout_seconds=%s",
            STREAM_STEP_TIMEOUT_SECONDS,
        )
        result = await asyncio.wait_for(
            agent.run(user_message),
            timeout=STREAM_STEP_TIMEOUT_SECONDS,
        )
        logger.warning(
            "[CHAT DEBUG] foundry_run_once_done result_type=%s len=%s",
            type(result).__name__,
            len(getattr(result, "text", "") or ""),
        )
        return getattr(result, "text", "") or ""

    async def _fake_stream(self, text: str) -> AsyncIterator[str]:
        """Emit a full response word by word to mimic streaming."""
        if not text:
            return
        words = text.split(" ")
        for index, word in enumerate(words):
            yield word + (" " if index < len(words) - 1 else "")
            await asyncio.sleep(0.025)
