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


def make_fake_agent(run_return: MagicMock) -> MagicMock:
    """Return a fake FoundryAgent with session and run helpers."""
    fake_agent = MagicMock()
    fake_agent.create_session = MagicMock(return_value="fake-session")
    fake_agent.get_session = MagicMock(return_value="fake-session")
    # Set side_effect directly so agent.run(...) raises; wrap run_return for return value
    fake_agent.run = MagicMock(return_value=run_return, side_effect=getattr(run_return, "side_effect", None))
    return fake_agent


class TestStreamChat:
    """Tests for ordered delivery and error handling."""

    @pytest.mark.asyncio
    async def test_stream_yields_deltas_then_final(self) -> None:
        run_stream = fake_response_stream_factory(
            yield_values=["Hello ", "world!"],
            final_text="Hello world!",
        )
        fake_agent = make_fake_agent(run_return=run_stream)

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
        fake_agent.create_session.assert_called_once()
        fake_agent.run.assert_called_once_with("Hi", stream=True, session="fake-session")

    @pytest.mark.asyncio
    async def test_final_text_is_emitted_when_stream_has_no_deltas(self) -> None:
        run_stream = fake_response_stream_factory(
            yield_values=[],
            final_text="done",
        )
        fake_agent = make_fake_agent(run_return=run_stream)

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
    async def test_stream_error_is_yielded_not_raised(self) -> None:
        fake_agent = MagicMock()
        fake_agent.create_session = MagicMock(return_value="fake-session")
        fake_agent.get_session = MagicMock(return_value="fake-session")
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
        run_stream = fake_response_stream_factory(
            yield_values=["", "hello"],
            final_text="hello",
        )
        fake_agent = make_fake_agent(run_return=run_stream)

        with (
            patch("app.services.foundry_stream.AIProjectClient", FakeProjectClient),
            patch("app.services.foundry_stream.FoundryAgent", return_value=fake_agent),
        ):
            service = FoundryStreamService(make_fake_client())
            events = [event async for event in service.stream_chat(user_message="Hi")]

        delta_events = [event for event in events if isinstance(event, StreamDelta)]
        assert len(delta_events) == 1
        assert delta_events[0].delta == "hello"
