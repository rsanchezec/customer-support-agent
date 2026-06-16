"""Unit tests for the Foundry streaming service.

All tests use mocked FoundryAgent and AIProjectClient objects, so no live
Foundry endpoint is contacted.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.foundry import FoundryClient
from app.services.foundry_stream import FoundryStreamService
from app.services.stream_events import StreamDelta, StreamError, StreamFinal


def make_fake_update(text: str) -> MagicMock:
    """Return a fake AgentResponseUpdate with the given text."""
    update = MagicMock()
    update.text = text
    return update


def make_fake_final(text: str) -> MagicMock:
    """Return a fake AgentResponse with the given text."""
    final = MagicMock()
    final.text = text
    return final


def fake_response_stream_factory(yield_values: list[str], final_text: str):
    """Build an async iterator that yields fake updates then a final response."""

    class FakeResponseStream:
        def __init__(self) -> None:
            self._iter = iter(yield_values)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return make_fake_update(next(self._iter))
            except StopIteration:
                raise StopAsyncIteration

        async def get_final_response(self):
            return make_fake_final(final_text)

    return FakeResponseStream()


class FakeProjectAgents:
    """Fake project_client.agents subclient."""

    async def get_version(self, *, agent_name: str, agent_version: str) -> MagicMock:
        return MagicMock(name=agent_name, version=agent_version)


class FakeProjectClient:
    """Fake async AIProjectClient context manager."""

    def __init__(self, **_: object) -> None:
        self.agents = FakeProjectAgents()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def make_fake_client() -> MagicMock:
    """Return the minimum FoundryClient shape used by FoundryStreamService."""
    fake_client = MagicMock(spec=FoundryClient)
    fake_client.endpoint = "https://example.test/project"
    fake_client.agent_name = "test-agent"
    fake_client.agent_version = "1"
    fake_client._credential = object()
    return fake_client


class TestStreamChat:
    """Tests for ordered delivery and error handling."""

    @pytest.mark.asyncio
    async def test_stream_yields_deltas_then_final(self) -> None:
        fake_agent = MagicMock()
        fake_agent.run = MagicMock(
            return_value=fake_response_stream_factory(
                yield_values=["Hello ", "world!"],
                final_text="Hello world!",
            )
        )

        with (
            patch("app.services.foundry_stream.AIProjectClient", FakeProjectClient),
            patch("app.services.foundry_stream.FoundryAgent", return_value=fake_agent),
        ):
            service = FoundryStreamService(make_fake_client())
            events = [event async for event in service.stream_chat(user_message="Hi")]

        assert len(events) == 3
        assert isinstance(events[0], StreamDelta)
        assert events[0].delta == "Hello "
        assert isinstance(events[1], StreamDelta)
        assert events[1].delta == "world!"
        assert isinstance(events[2], StreamFinal)
        assert events[2].text == "Hello world!"
        assert events[2].service_session_id is None
        fake_agent.run.assert_called_once_with("Hi", stream=True)

    @pytest.mark.asyncio
    async def test_final_text_is_emitted_when_stream_has_no_deltas(self) -> None:
        fake_agent = MagicMock()
        fake_agent.run = MagicMock(
            return_value=fake_response_stream_factory(
                yield_values=[],
                final_text="done",
            )
        )

        with (
            patch("app.services.foundry_stream.AIProjectClient", FakeProjectClient),
            patch("app.services.foundry_stream.FoundryAgent", return_value=fake_agent),
        ):
            service = FoundryStreamService(make_fake_client())
            events = [event async for event in service.stream_chat(user_message="Hi")]

        assert len(events) == 2
        assert isinstance(events[0], StreamDelta)
        assert events[0].delta == "done"
        assert isinstance(events[1], StreamFinal)
        assert events[1].text == "done"

    @pytest.mark.asyncio
    async def test_falls_back_to_run_when_stream_api_is_unavailable(self) -> None:
        async def run_once(_: str):
            return make_fake_final("fallback text")

        def run(message: str, **kwargs: object):
            if kwargs.get("stream"):
                raise AttributeError("stream unavailable")
            return run_once(message)

        fake_agent = MagicMock()
        fake_agent.run = MagicMock(side_effect=run)

        with (
            patch("app.services.foundry_stream.AIProjectClient", FakeProjectClient),
            patch("app.services.foundry_stream.FoundryAgent", return_value=fake_agent),
        ):
            service = FoundryStreamService(make_fake_client())
            events = [event async for event in service.stream_chat(user_message="Hi")]

        deltas = [event for event in events if isinstance(event, StreamDelta)]
        assert "".join(event.delta for event in deltas) == "fallback text"
        assert isinstance(events[-1], StreamFinal)
        assert events[-1].text == "fallback text"
        assert fake_agent.run.call_args_list[0].kwargs == {"stream": True}
        assert fake_agent.run.call_args_list[1].kwargs == {}

    @pytest.mark.asyncio
    async def test_stream_error_is_yielded_not_raised(self) -> None:
        fake_agent = MagicMock()
        fake_agent.run = MagicMock(side_effect=RuntimeError("Foundry unreachable"))

        with (
            patch("app.services.foundry_stream.AIProjectClient", FakeProjectClient),
            patch("app.services.foundry_stream.FoundryAgent", return_value=fake_agent),
        ):
            service = FoundryStreamService(make_fake_client())
            events = [event async for event in service.stream_chat(user_message="Hi")]

        assert len(events) == 1
        assert isinstance(events[0], StreamError)
        assert "Foundry unreachable" in events[0].message

    @pytest.mark.asyncio
    async def test_empty_deltas_are_skipped(self) -> None:
        fake_agent = MagicMock()
        fake_agent.run = MagicMock(
            return_value=fake_response_stream_factory(
                yield_values=["", "hello"],
                final_text="hello",
            )
        )

        with (
            patch("app.services.foundry_stream.AIProjectClient", FakeProjectClient),
            patch("app.services.foundry_stream.FoundryAgent", return_value=fake_agent),
        ):
            service = FoundryStreamService(make_fake_client())
            events = [event async for event in service.stream_chat(user_message="Hi")]

        delta_events = [event for event in events if isinstance(event, StreamDelta)]
        assert len(delta_events) == 1
        assert delta_events[0].delta == "hello"
