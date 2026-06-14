"""Stream event models for the Foundry streaming service.

Yields from :class:`FoundryStreamService.stream_chat` are one of the
dataclass variants defined here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StreamEvent:
    """Root type for all events emitted during a streaming chat turn."""

    pass


@dataclass(frozen=True)
class StreamDelta(StreamEvent):
    """A partial text update from the agent."""

    delta: str


@dataclass(frozen=True)
class StreamFinal(StreamEvent):
    """The completed agent response, returned after the stream finishes."""

    text: str
    service_session_id: str | None


@dataclass(frozen=True)
class StreamError(StreamEvent):
    """A non-recoverable error that occurred during the turn."""

    message: str


# ---------------------------------------------------------------------------
# Factory helpers (match the spec language)
# ---------------------------------------------------------------------------


def delta(text: str) -> StreamDelta:
    """Create a delta event holding one text fragment."""
    return StreamDelta(delta=text)


def final(text: str, service_session_id: str | None = None) -> StreamFinal:
    """Create the final event with aggregated text and the Foundry session id."""
    return StreamFinal(text=text, service_session_id=service_session_id)


def error(message: str) -> StreamError:
    """Create an error event with a human-readable message."""
    return StreamError(message=message)
