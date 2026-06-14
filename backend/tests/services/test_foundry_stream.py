"""Unit tests for the Foundry streaming service.

All tests use fully-mocked FoundryAgent and streaming primitives — no live
Foundry endpoint is contacted.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.foundry import FoundryClient
from app.services.foundry_stream import FoundryStreamService
from app.services.stream_events import StreamDelta, StreamError, StreamFinal


def make_fake_update(text: str) -> MagicMock:
    """Return a fake ``AgentResponseUpdate`` with the given text."""
    update = MagicMock()
    update.text = text
    return update


def make_fake_final(text: str) -> MagicMock:
    """Return a fake ``AgentResponse`` (final response)."""
    final = MagicMock()
    final.text = text
    return final


def fake_response_stream_factory(yield_values: list[str], final_text: str):
    """Build an async iterator that yields fake updates then returns a final response."""

    class FakeResponseStream:
        def __init__(self) -> None:
            self._iter = iter(yield_values)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                text = next(self._iter)
                return make_fake_update(text)
            except StopIteration:
                raise StopAsyncIteration

        async def get_final_response(self):
            return make_fake_final(final_text)

    return FakeResponseStream()


class FakeSession:
    """Fake session object returned by agent.create_session() / get_session()."""

    def __init__(self, service_session_id: str = "f-sid-001") -> None:
        self.service_session_id = service_session_id


class TestStreamChatYieldsDeltasThenFinal:
    """Tests for the ordered delivery of stream events."""

    @pytest.mark.asyncio
    async def test_stream_yields_deltas_then_final(self) -> None:
        """The service yields delta events in order, then one final event."""
        # Arrange
        fake_client = MagicMock(spec=FoundryClient)
        fake_client.agent_name = "test-agent"
        fake_client.agent_version = "1"
        fake_client._ensure_client = AsyncMock()  # type: ignore[method-assign]

        service = FoundryStreamService(fake_client)

        # Build a fake stream that yields two text fragments then completes.
        fake_stream = fake_response_stream_factory(
            yield_values=["Hello ", "world!"],
            final_text="Hello world!",
        )

        fake_agent = MagicMock()
        fake_agent.create_session = MagicMock(return_value=FakeSession("f-sid-001"))
        fake_agent.get_session = MagicMock(return_value=FakeSession("f-sid-001"))
        fake_agent.run = MagicMock(return_value=fake_stream)

        with patch("app.services.foundry_stream.FoundryAgent", return_value=fake_agent):
            events = []
            async for event in service.stream_chat(user_message="Hi"):
                events.append(event)

        # Assert
        assert len(events) == 3
        assert isinstance(events[0], StreamDelta)
        assert events[0].delta == "Hello "
        assert isinstance(events[1], StreamDelta)
        assert events[1].delta == "world!"
        assert isinstance(events[2], StreamFinal)
        assert events[2].text == "Hello world!"
        assert events[2].service_session_id == "f-sid-001"

    @pytest.mark.asyncio
    async def test_stream_creates_new_session_when_no_service_id(self) -> None:
        """When service_session_id is None, a fresh Foundry session is created."""
        fake_client = MagicMock(spec=FoundryClient)
        fake_client.agent_name = "test-agent"
        fake_client.agent_version = "1"
        fake_client._ensure_client = AsyncMock()  # type: ignore[method-assign]

        service = FoundryStreamService(fake_client)

        fake_stream = fake_response_stream_factory([], "done")
        fake_agent = MagicMock()
        fake_agent.create_session = MagicMock(return_value=FakeSession("fresh-sid"))
        fake_agent.run = MagicMock(return_value=fake_stream)

        with patch("app.services.foundry_stream.FoundryAgent", return_value=fake_agent):
            async for _ in service.stream_chat(user_message="Hi", service_session_id=None):
                pass

        fake_agent.create_session.assert_called_once()
        fake_agent.get_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_reuses_session_when_service_id_provided(self) -> None:
        """When service_session_id is provided, the existing session is reused."""
        fake_client = MagicMock(spec=FoundryClient)
        fake_client.agent_name = "test-agent"
        fake_client.agent_version = "1"
        fake_client._ensure_client = AsyncMock()  # type: ignore[method-assign]

        service = FoundryStreamService(fake_client)

        fake_stream = fake_response_stream_factory([], "done")
        fake_agent = MagicMock()
        fake_agent.create_session = MagicMock()
        fake_agent.get_session = MagicMock(return_value=FakeSession("existing-sid"))
        fake_agent.run = MagicMock(return_value=fake_stream)

        with patch("app.services.foundry_stream.FoundryAgent", return_value=fake_agent):
            async for _ in service.stream_chat(
                user_message="Hi", service_session_id="existing-sid"
            ):
                pass

        fake_agent.get_session.assert_called_once_with(service_session_id="existing-sid")
        fake_agent.create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_error_is_yielded_not_raised(self) -> None:
        """Any exception during streaming is caught and yielded as StreamError."""
        fake_client = MagicMock(spec=FoundryClient)
        fake_client.agent_name = "test-agent"
        fake_client.agent_version = "1"
        fake_client._ensure_client = AsyncMock()  # type: ignore[method-assign]

        service = FoundryStreamService(fake_client)

        fake_agent = MagicMock()
        fake_agent.create_session = MagicMock(return_value=FakeSession())
        fake_agent.run = MagicMock(side_effect=RuntimeError("Foundry unreachable"))

        with patch("app.services.foundry_stream.FoundryAgent", return_value=fake_agent):
            events = []
            async for event in service.stream_chat(user_message="Hi"):
                events.append(event)

        assert len(events) == 1
        assert isinstance(events[0], StreamError)
        assert "Foundry unreachable" in events[0].message

    @pytest.mark.asyncio
    async def test_empty_deltas_are_skipped(self) -> None:
        """Updates with empty text do not produce a delta event."""
        fake_client = MagicMock(spec=FoundryClient)
        fake_client.agent_name = "test-agent"
        fake_client.agent_version = "1"
        fake_client._ensure_client = AsyncMock()  # type: ignore[method-assign]

        service = FoundryStreamService(fake_client)

        # One empty update followed by a real one.
        fake_stream = fake_response_stream_factory(
            yield_values=["", "hello"],
            final_text="hello",
        )

        fake_agent = MagicMock()
        fake_agent.create_session = MagicMock(return_value=FakeSession())
        fake_agent.run = MagicMock(return_value=fake_stream)

        with patch("app.services.foundry_stream.FoundryAgent", return_value=fake_agent):
            events = []
            async for event in service.stream_chat(user_message="Hi"):
                events.append(event)

        delta_events = [e for e in events if isinstance(e, StreamDelta)]
        assert len(delta_events) == 1
        assert delta_events[0].delta == "hello"
