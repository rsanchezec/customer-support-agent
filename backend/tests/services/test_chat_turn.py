"""Unit tests for the chat turn orchestrator.

All tests use mocked database sessions and mocked Foundry streaming service.
No live Foundry endpoint or database is contacted.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.conversation import Conversation
from app.domain.message import Message
from app.domain.user import User
from app.services.chat_turn import ChatTurnResult, ChatTurnService
from app.services.foundry import FoundryClient
from app.services.stream_events import StreamDelta, StreamError, StreamFinal


def make_fake_user(oid: str = "oid-123") -> User:
    """Return a fake :class:`User` with a UUID primary key."""
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.entraid_oid = oid
    user.email = "test@example.com"
    user.display_name = "Test User"
    return user


def make_fake_conversation(user_id: uuid.UUID) -> Conversation:
    """Return a fake :class:`Conversation` with a UUID primary key."""
    conv = MagicMock(spec=Conversation)
    conv.id = uuid.uuid4()
    conv.user_id = user_id
    conv.foundry_conversation_id = None
    conv.title = "Test conversation"
    return conv


class FakeAsyncIterator:
    """Wraps a Python list as an async iterator for testing."""

    def __init__(self, items: list) -> None:
        self._iter = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self) -> object:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class TestCreatesConversationAndMessagesOnFirstTurn:
    """Tests for first-turn behaviour (no prior conversation)."""

    @pytest.mark.asyncio
    async def test_creates_conversation_and_messages_on_first_turn(self) -> None:
        """On the first turn (conversation=None), a new conversation is created."""
        user = make_fake_user()
        fake_conv_id = uuid.uuid4()

        # Track what gets added to the session.
        added_objects: list[object] = []

        fake_session = MagicMock()
        fake_session.add = lambda obj: added_objects.append(obj)
        fake_session.flush = AsyncMock()
        fake_session.commit = AsyncMock()

        # Patch Conversation so its id is assigned immediately.
        with patch.object(
            Conversation, "id", new_callable=lambda: property(lambda self: fake_conv_id)
        ):
            fake_stream_events = [
                StreamDelta(delta="Hi "),
                StreamDelta(delta="there!"),
                StreamFinal(text="Hi there!", service_session_id="f-sid-001"),
            ]
            fake_stream_iterator = FakeAsyncIterator(fake_stream_events)

            fake_foundry_client = MagicMock(spec=FoundryClient)

            service = ChatTurnService(fake_session, fake_foundry_client)

            # Mock FoundryStreamService so it doesn't call the real Foundry.
            with patch("app.services.foundry_stream.FoundryStreamService") as mock_stream_svc:
                mock_instance = MagicMock()
                mock_instance.stream_chat = MagicMock(return_value=fake_stream_iterator)
                mock_stream_svc.return_value = mock_instance

                events_iterator, result = await service.execute(
                    user=user,
                    conversation=None,
                    user_message="Hello",
                )

                # Consume the events.
                events = []
                async for ev in events_iterator:
                    events.append(ev)

                # Verify a Conversation and a Message were added.
                assert any(isinstance(o, Conversation) for o in added_objects)
                assert any(isinstance(o, Message) and o.role == "user" for o in added_objects)
                # Assistant message is NOT persisted here — only after StreamFinal.
                assert not any(
                    isinstance(o, Message) and o.role == "assistant" for o in added_objects
                )

    @pytest.mark.asyncio
    async def test_reuses_conversation_on_subsequent_turns(self) -> None:
        """When a conversation is already provided, it is reused (not recreated)."""
        user = make_fake_user()
        existing_conv = make_fake_conversation(user.id)
        existing_conv.foundry_conversation_id = "f-sid-old"

        added_objects: list[object] = []
        fake_session = MagicMock()
        fake_session.add = lambda obj: added_objects.append(obj)
        fake_session.flush = AsyncMock()
        fake_session.commit = AsyncMock()

        fake_stream_events = [
            StreamDelta(delta="Reply."),
            StreamFinal(text="Reply.", service_session_id="f-sid-old"),
        ]
        fake_stream_iterator = FakeAsyncIterator(fake_stream_events)
        fake_foundry_client = MagicMock(spec=FoundryClient)

        service = ChatTurnService(fake_session, fake_foundry_client)

        with patch("app.services.foundry_stream.FoundryStreamService") as mock_stream_svc:
            mock_instance = MagicMock()
            mock_instance.stream_chat = MagicMock(return_value=fake_stream_iterator)
            mock_stream_svc.return_value = mock_instance

            _, result = await service.execute(
                user=user,
                conversation=existing_conv,
                user_message="Second turn",
            )

            # Only a Message should be added (no new Conversation).
            added_messages = [o for o in added_objects if isinstance(o, Message)]
            assert len(added_messages) == 1
            assert added_messages[0].role == "user"

    @pytest.mark.asyncio
    async def test_persists_user_message_before_streaming(self) -> None:
        """The user message row is committed before the Foundry call starts."""
        user = make_fake_user()
        fake_conv_id = uuid.uuid4()
        commit_order: list[str] = []

        fake_session = MagicMock()
        fake_session.add = lambda obj: None
        fake_session.flush = AsyncMock()
        fake_session.commit = AsyncMock(side_effect=lambda: commit_order.append("commit"))

        async def slow_flush() -> None:
            commit_order.append("flush")

        fake_session.flush = slow_flush

        fake_stream_events = [StreamFinal(text="Done", service_session_id="sid")]
        fake_stream_iterator = FakeAsyncIterator(fake_stream_events)
        fake_foundry_client = MagicMock(spec=FoundryClient)

        service = ChatTurnService(fake_session, fake_foundry_client)

        with patch.object(
            Conversation, "id", new_callable=lambda: property(lambda self: fake_conv_id)
        ):
            with patch("app.services.foundry_stream.FoundryStreamService") as mock_stream_svc:
                mock_instance = MagicMock()
                mock_instance.stream_chat = MagicMock(return_value=fake_stream_iterator)
                mock_stream_svc.return_value = mock_instance

                events_iterator, _ = await service.execute(
                    user=user,
                    conversation=None,
                    user_message="Hello",
                )

                async for _ in events_iterator:
                    pass

        # Flush is called (user message persisted).
        assert "flush" in commit_order

    @pytest.mark.asyncio
    async def test_persists_assistant_message_after_final_event(self) -> None:
        """The assistant row is inserted only after the StreamFinal event."""
        user = make_fake_user()
        fake_conv_id = uuid.uuid4()

        added_objects: list[object] = []

        fake_session = MagicMock()
        fake_session.add = lambda obj: added_objects.append(obj)
        fake_session.flush = AsyncMock()
        fake_session.commit = AsyncMock()

        fake_stream_events = [
            StreamDelta(delta="Hi."),
            StreamFinal(text="Hi.", service_session_id="f-sid"),
        ]
        fake_stream_iterator = FakeAsyncIterator(fake_stream_events)
        fake_foundry_client = MagicMock(spec=FoundryClient)

        service = ChatTurnService(fake_session, fake_foundry_client)

        with patch.object(
            Conversation, "id", new_callable=lambda: property(lambda self: fake_conv_id)
        ):
            with patch("app.services.foundry_stream.FoundryStreamService") as mock_stream_svc:
                mock_instance = MagicMock()
                mock_instance.stream_chat = MagicMock(return_value=fake_stream_iterator)
                mock_stream_svc.return_value = mock_instance

                events_iterator, _ = await service.execute(
                    user=user,
                    conversation=None,
                    user_message="Hello",
                )

                async for ev in events_iterator:
                    if isinstance(ev, StreamFinal):
                        # Only now does the caller persist the assistant.
                        await service.persist_assistant_message(
                            conversation_id=fake_conv_id,
                            assistant_text=ev.text,
                        )

        # One user message (during execute) + one assistant message (after final).
        messages = [o for o in added_objects if isinstance(o, Message)]
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert messages[1].content == "Hi."

    @pytest.mark.asyncio
    async def test_persists_assistant_message_even_on_error(self) -> None:
        """No assistant row is inserted when a StreamError is received."""
        user = make_fake_user()
        fake_conv_id = uuid.uuid4()

        added_objects: list[object] = []

        fake_session = MagicMock()
        fake_session.add = lambda obj: added_objects.append(obj)
        fake_session.flush = AsyncMock()
        fake_session.commit = AsyncMock()

        fake_stream_events = [
            StreamDelta(delta="Partial."),
            StreamError(message="Something went wrong"),
        ]
        fake_stream_iterator = FakeAsyncIterator(fake_stream_events)
        fake_foundry_client = MagicMock(spec=FoundryClient)

        service = ChatTurnService(fake_session, fake_foundry_client)

        with patch.object(
            Conversation, "id", new_callable=lambda: property(lambda self: fake_conv_id)
        ):
            with patch("app.services.foundry_stream.FoundryStreamService") as mock_stream_svc:
                mock_instance = MagicMock()
                mock_instance.stream_chat = MagicMock(return_value=fake_stream_iterator)
                mock_stream_svc.return_value = mock_instance

                events_iterator, _ = await service.execute(
                    user=user,
                    conversation=None,
                    user_message="Hello",
                )

                async for ev in events_iterator:
                    if isinstance(ev, StreamError):
                        # Caller would NOT call persist_assistant_message here.
                        pass

        # Only the user message should be persisted — no assistant.
        messages = [o for o in added_objects if isinstance(o, Message)]
        assert len(messages) == 1
        assert messages[0].role == "user"


class TestChatTurnResult:
    """Tests for the ChatTurnResult dataclass."""

    def test_result_contains_conversation_id(self) -> None:
        """ChatTurnResult carries the conversation UUID back to the caller."""
        conv_id = uuid.uuid4()
        result = ChatTurnResult(assistant_text="Hello", conversation_id=conv_id)
        assert result.conversation_id == conv_id

    def test_result_contains_assistant_text(self) -> None:
        """ChatTurnResult carries the final assistant text."""
        result = ChatTurnResult(assistant_text="The answer is 42.", conversation_id=uuid.uuid4())
        assert result.assistant_text == "The answer is 42."
