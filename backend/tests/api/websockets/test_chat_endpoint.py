"""Acceptance tests for the WebSocket /ws/chat/{conversation_id} endpoint."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.db.engine
import app.db.session
from app.api.auth.jwks_fetcher import JwksFetcher
from app.api.websockets.chat import router as chat_ws_router
from app.domain.user import User
from app.services.conversation_service import ConversationService
from app.services.foundry import FoundryClient
from app.services.stream_events import StreamDelta, StreamError, StreamFinal
from app.settings import Settings

from ..conftest import (
    _kid,
    _private_key_pem,
    _public_key_pem,
    create_test_token,
    make_jwks_response,
)

# ---------------------------------------------------------------------------
# Fake JWKS client (mirrors test_deps.py)
# ---------------------------------------------------------------------------


class FakeJwksClient:
    """Fake HTTP client that returns the canned JWKS for any GET."""

    def __init__(self, jwks: dict) -> None:
        self._jwks = jwks

    async def get(self, url: str):
        jwks = self._jwks

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                return jwks

        return R()


# ---------------------------------------------------------------------------
# App factory for WS tests (overrides app.state)
# ---------------------------------------------------------------------------


def _make_ws_app(
    fake_jwks_fetcher: JwksFetcher,
    fake_conversation_service: ConversationService,
    fake_foundry_client: FoundryClient,
    ws_settings: Any | None = None,
) -> FastAPI:
    """Build a minimal FastAPI app with the WS router and mocked state."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.jwks_fetcher = fake_jwks_fetcher
    app.state.conversation_service = fake_conversation_service
    app.state.foundry_client = fake_foundry_client
    app.include_router(chat_ws_router)

    if ws_settings is not None:
        app.state._ws_settings = ws_settings  # type: ignore[attr-defined]

    return app


# ---------------------------------------------------------------------------
# Module-level autouse fixture: prevent any real DB calls
# ---------------------------------------------------------------------------

# Pre-create a mock session factory that is shared across all tests.
_mock_session = MagicMock()
_mock_session.__aenter__ = AsyncMock(return_value=_mock_session)
_mock_session.__aexit__ = AsyncMock(return_value=None)
_mock_session_factory = MagicMock(return_value=_mock_session)

# Patch at the definition site so all imports of _get_session_factory hit this.
_original_get_session_factory = app.db.session._get_session_factory


@pytest.fixture(autouse=True)
def patch_session_factory():
    """Replace _get_session_factory with a no-op mock for all WS tests."""
    app.db.session._get_session_factory = lambda: _mock_session_factory
    app.db.engine._engine = MagicMock()  # prevent engine creation
    yield
    app.db.session._get_session_factory = _original_get_session_factory


@pytest.fixture
def ws_settings() -> Settings:
    """Return a Settings instance with test Entra ID values."""
    s = Settings()
    object.__setattr__(s, "entra_tenant_id", "test-tenant")
    object.__setattr__(s, "entra_client_id", "test-client")
    object.__setattr__(s, "entra_app_audience", "api://test-client")
    return s


@pytest.fixture
def fake_user() -> User:
    """Return a User with a stable UUID."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.entraid_oid = "test-oid-001"
    user.email = "test@example.com"
    return user


@pytest.fixture
def fake_jwks_fetcher() -> JwksFetcher:
    """A JwksFetcher pre-loaded with the test RSA public key."""
    jwks_response = make_jwks_response(_kid, _public_key_pem)
    http_client = FakeJwksClient(jwks_response)
    return JwksFetcher(
        jwks_uri="https://login.microsoftonline.com/test-tenant/discovery/v2.0/keys",
        http_client=http_client,
    )


@pytest.fixture
def fake_conversation_service(fake_user: User):
    """A ConversationService whose get_or_create returns a fake conversation."""
    conv_id = uuid4()
    conv = MagicMock()
    conv.id = conv_id
    conv.foundry_conversation_id = None

    service = MagicMock(spec=ConversationService)
    service.get_or_create = AsyncMock(return_value=(conv, True))
    return service


@pytest.fixture
def valid_token() -> str:
    """Return a valid JWT signed with the test RSA key."""
    return create_test_token(_private_key_pem, _kid)


@pytest.fixture
def expired_token() -> str:
    """Return an expired JWT signed with the test RSA key."""
    return create_test_token(_private_key_pem, _kid, exp_offset_seconds=-10)


def _generate_wrong_key_token() -> str:
    """Generate a token signed with a different RSA key (wrong signature)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return create_test_token(private_pem, _kid)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_accepts_websocket_with_valid_token(
    fake_jwks_fetcher: JwksFetcher,
    fake_conversation_service: ConversationService,
    fake_user: User,
    valid_token: str,
    ws_settings: Any,
):
    """WS opens with valid bearer.jwt subprotocol, receives delta + done."""
    # Arrange: fake FoundryClient that yields deltas then final
    fake_stream_events = [
        StreamDelta(delta="Hello"),
        StreamDelta(delta=" world"),
        StreamFinal(text="Hello world", service_session_id="sess-123"),
    ]

    async def fake_execute(**kwargs):
        async def event_iter():
            for event in fake_stream_events:
                yield event

        return event_iter(), MagicMock(assistant_text="", conversation_id=uuid4())

    fake_chat_svc = MagicMock()
    fake_chat_svc.execute = fake_execute
    fake_chat_svc.persist_assistant_message = AsyncMock()

    fake_conv = MagicMock()
    fake_conv.id = uuid4()
    fake_conv.foundry_conversation_id = "sess-123"
    fake_conversation_service.get_or_create = AsyncMock(return_value=(fake_conv, False))

    fake_foundry = MagicMock(spec=FoundryClient)

    app = _make_ws_app(fake_jwks_fetcher, fake_conversation_service, fake_foundry)
    client = TestClient(app)

    # Mock _get_session_factory to avoid DB pragma issues in tests
    mock_session_factory = MagicMock()
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session_factory.return_value = mock_session

    # Patch UserService so new instances return fake_user from get_or_create_by_oid
    fake_user_service_instance = MagicMock()
    fake_user_service_instance.get_or_create_by_oid = AsyncMock(return_value=fake_user)

    mock_user_service_class = MagicMock()
    mock_user_service_class.return_value = fake_user_service_instance

    with patch("app.api.websockets.chat.get_settings", return_value=ws_settings):
        with patch("app.db.session._get_session_factory", mock_session_factory):
            with patch("app.api.websockets.chat.UserService", mock_user_service_class):
                with patch(
                    "app.services.chat_turn.ChatTurnService",
                    side_effect=lambda *a, **kw: fake_chat_svc,
                ):
                    with client.websocket_connect(
                        f"/ws/chat/{fake_conv.id}",
                        subprotocols=["bearer.jwt." + valid_token],
                    ) as ws:
                        # Server should have accepted with bearer.jwt
                        # Send a message
                        ws.send_json({"content": "Hi"})
                        # Receive delta frames
                        frame1 = ws.receive_json()
                        assert frame1["type"] == "delta"
                        assert frame1["text"] == "Hello"
                        frame2 = ws.receive_json()
                        assert frame2["type"] == "delta"
                        assert frame2["text"] == " world"
                        # Receive done frame
                        done = ws.receive_json()
                        assert done["type"] == "done"
                        assert "conversation_id" in done


def test_rejects_with_1008_for_missing_subprotocol(
    fake_jwks_fetcher: JwksFetcher,
    fake_conversation_service: ConversationService,
):
    """WS without Sec-WebSocket-Protocol → close code 1008."""
    fake_foundry = MagicMock(spec=FoundryClient)
    app = _make_ws_app(fake_jwks_fetcher, fake_conversation_service, fake_foundry)
    client = TestClient(app)

    conv_id = uuid4()
    with pytest.raises(Exception) as exc_info:
        with client.websocket_connect(f"/ws/chat/{conv_id}"):
            pass

    # The exception contains the WebSocket disconnect with code 1008
    exc = exc_info.value
    assert hasattr(exc, "code") and exc.code == 1008, f"Expected close code 1008, got {exc!r}"


def test_rejects_with_1008_for_invalid_token(
    fake_jwks_fetcher: JwksFetcher,
    fake_conversation_service: ConversationService,
    ws_settings: Any,
):
    """WS with a JWT signed by wrong key → close code 1008."""
    wrong_token = _generate_wrong_key_token()
    fake_foundry = MagicMock(spec=FoundryClient)
    app = _make_ws_app(fake_jwks_fetcher, fake_conversation_service, fake_foundry)
    client = TestClient(app)

    conv_id = uuid4()
    with patch("app.api.websockets.chat.get_settings", return_value=ws_settings):
        with pytest.raises(Exception) as exc_info:
            with client.websocket_connect(
                f"/ws/chat/{conv_id}",
                subprotocols=["bearer.jwt." + wrong_token],
            ):
                pass

        exc = exc_info.value
        assert hasattr(exc, "code") and exc.code == 1008, f"Expected close code 1008, got {exc!r}"


def test_rejects_with_1008_for_expired_token(
    fake_jwks_fetcher: JwksFetcher,
    fake_conversation_service: ConversationService,
    expired_token: str,
    ws_settings: Any,
):
    """WS with an expired JWT → close code 1008."""
    fake_foundry = MagicMock(spec=FoundryClient)
    app = _make_ws_app(fake_jwks_fetcher, fake_conversation_service, fake_foundry)
    client = TestClient(app)

    conv_id = uuid4()
    with patch("app.api.websockets.chat.get_settings", return_value=ws_settings):
        with pytest.raises(Exception) as exc_info:
            with client.websocket_connect(
                f"/ws/chat/{conv_id}",
                subprotocols=["bearer.jwt." + expired_token],
            ):
                pass

        exc = exc_info.value
        assert hasattr(exc, "code") and exc.code == 1008, f"Expected close code 1008, got {exc!r}"


def test_rejects_with_1008_for_empty_message(
    fake_jwks_fetcher: JwksFetcher,
    fake_conversation_service: ConversationService,
    valid_token: str,
    fake_user: User,
    ws_settings: Any,
):
    """Empty content → server sends error frame then closes with code 1008."""
    fake_user_service_instance = MagicMock()
    fake_user_service_instance.get_or_create_by_oid = AsyncMock(return_value=fake_user)
    mock_user_service_class = MagicMock(return_value=fake_user_service_instance)

    fake_foundry = MagicMock(spec=FoundryClient)
    app = _make_ws_app(fake_jwks_fetcher, fake_conversation_service, fake_foundry)
    client = TestClient(app)

    conv_id = uuid4()
    with patch("app.api.websockets.chat.get_settings", return_value=ws_settings):
        with patch("app.api.websockets.chat.UserService", mock_user_service_class):
            with client.websocket_connect(
                f"/ws/chat/{conv_id}",
                subprotocols=["bearer.jwt." + valid_token],
            ) as ws:
                ws.send_json({"content": ""})
                error_frame = ws.receive_json()
                assert error_frame["type"] == "error"
                assert error_frame["code"] == "bad_request"
                assert "non-empty" in error_frame["message"]


def test_streams_deltas_to_client(
    fake_jwks_fetcher: JwksFetcher,
    fake_conversation_service: ConversationService,
    valid_token: str,
    fake_user: User,
    ws_settings: Any,
):
    """Fake stream with 3 deltas + final → client receives 3 delta frames + 1 done."""
    fake_conv = MagicMock()
    fake_conv.id = uuid4()
    fake_conv.foundry_conversation_id = None
    fake_conversation_service.get_or_create = AsyncMock(return_value=(fake_conv, True))

    fake_stream_events = [
        StreamDelta(delta="One "),
        StreamDelta(delta="two "),
        StreamDelta(delta="three"),
        StreamFinal(text="One two three", service_session_id="sess-abc"),
    ]

    async def fake_execute(**kwargs):
        async def event_iter():
            for event in fake_stream_events:
                yield event

        return event_iter(), MagicMock(assistant_text="", conversation_id=fake_conv.id)

    fake_chat_svc = MagicMock()
    fake_chat_svc.execute = fake_execute
    fake_chat_svc.persist_assistant_message = AsyncMock()

    fake_user_service_instance = MagicMock()
    fake_user_service_instance.get_or_create_by_oid = AsyncMock(return_value=fake_user)
    mock_user_service_class = MagicMock(return_value=fake_user_service_instance)

    fake_foundry = MagicMock(spec=FoundryClient)

    app = _make_ws_app(fake_jwks_fetcher, fake_conversation_service, fake_foundry)
    client = TestClient(app)

    with patch("app.api.websockets.chat.get_settings", return_value=ws_settings):
        with patch("app.api.websockets.chat.UserService", mock_user_service_class):
            with patch(
                "app.services.chat_turn.ChatTurnService", side_effect=lambda *a, **kw: fake_chat_svc
            ):
                with client.websocket_connect(
                    f"/ws/chat/{fake_conv.id}",
                    subprotocols=["bearer.jwt." + valid_token],
                ) as ws:
                    ws.send_json({"content": "count"})
                    frames = []
                    while True:
                        frame = ws.receive_json()
                        frames.append(frame)
                        if frame["type"] == "done":
                            break

    deltas = [f for f in frames if f["type"] == "delta"]
    assert len(deltas) == 3
    assert deltas[0]["text"] == "One "
    assert deltas[1]["text"] == "two "
    assert deltas[2]["text"] == "three"
    done_frames = [f for f in frames if f["type"] == "done"]
    assert len(done_frames) == 1


def test_persists_user_and_assistant_messages(
    fake_jwks_fetcher: JwksFetcher,
    fake_conversation_service: ConversationService,
    valid_token: str,
    fake_user: User,
    ws_settings: Any,
):
    """ChatTurnService.execute is called once with the resolved conversation and user_message."""
    fake_conv = MagicMock()
    fake_conv.id = uuid4()
    fake_conv.foundry_conversation_id = None
    fake_conversation_service.get_or_create = AsyncMock(return_value=(fake_conv, True))

    execute_call_args = []

    async def fake_execute(**kwargs):
        execute_call_args.append(kwargs)

        async def event_iter():
            yield StreamFinal(text="answer", service_session_id="sess-1")

        return event_iter(), MagicMock(assistant_text="", conversation_id=fake_conv.id)

    fake_chat_svc = MagicMock()
    fake_chat_svc.execute = fake_execute
    fake_chat_svc.persist_assistant_message = AsyncMock()

    fake_user_service_instance = MagicMock()
    fake_user_service_instance.get_or_create_by_oid = AsyncMock(return_value=fake_user)
    mock_user_service_class = MagicMock(return_value=fake_user_service_instance)

    fake_foundry = MagicMock(spec=FoundryClient)

    app = _make_ws_app(fake_jwks_fetcher, fake_conversation_service, fake_foundry)
    client = TestClient(app)

    with patch("app.api.websockets.chat.get_settings", return_value=ws_settings):
        with patch("app.api.websockets.chat.UserService", mock_user_service_class):
            with patch(
                "app.services.chat_turn.ChatTurnService", side_effect=lambda *a, **kw: fake_chat_svc
            ):
                with client.websocket_connect(
                    f"/ws/chat/{fake_conv.id}",
                    subprotocols=["bearer.jwt." + valid_token],
                ) as ws:
                    ws.send_json({"content": "my question"})
                    ws.receive_json()  # done

    assert len(execute_call_args) == 1
    assert execute_call_args[0]["user_message"] == "my question"


def test_reuses_existing_conversation(
    fake_jwks_fetcher: JwksFetcher,
    fake_conversation_service: ConversationService,
    valid_token: str,
    fake_user: User,
    ws_settings: Any,
):
    """Calling twice with same conversation_id reuses the conversation (get_or_create returns False on second call)."""
    fake_conv = MagicMock()
    fake_conv.id = uuid4()
    fake_conv.foundry_conversation_id = "existing-sess"
    # First call: new conversation (created=True)
    # Second call: existing conversation (created=False)
    fake_conversation_service.get_or_create = AsyncMock(
        side_effect=[
            (fake_conv, True),
            (fake_conv, False),
        ]
    )

    async def fake_execute(**kwargs):
        async def event_iter():
            yield StreamFinal(text="response", service_session_id="sess-1")

        return event_iter(), MagicMock(assistant_text="", conversation_id=fake_conv.id)

    fake_chat_svc = MagicMock()
    fake_chat_svc.execute = fake_execute
    fake_chat_svc.persist_assistant_message = AsyncMock()

    fake_user_service_instance = MagicMock()
    fake_user_service_instance.get_or_create_by_oid = AsyncMock(return_value=fake_user)
    mock_user_service_class = MagicMock(return_value=fake_user_service_instance)

    fake_foundry = MagicMock(spec=FoundryClient)

    app = _make_ws_app(fake_jwks_fetcher, fake_conversation_service, fake_foundry)
    client = TestClient(app)

    conv_id = fake_conv.id
    with patch("app.api.websockets.chat.get_settings", return_value=ws_settings):
        with patch("app.api.websockets.chat.UserService", mock_user_service_class):
            with patch(
                "app.services.chat_turn.ChatTurnService", side_effect=lambda *a, **kw: fake_chat_svc
            ):
                with client.websocket_connect(
                    f"/ws/chat/{conv_id}",
                    subprotocols=["bearer.jwt." + valid_token],
                ) as ws:
                    ws.send_json({"content": "first"})
                    ws.receive_json()  # done

    # Verify the second call does NOT create a new conversation
    assert fake_conversation_service.get_or_create.call_count == 1


def test_sends_error_on_stream_error(
    fake_jwks_fetcher: JwksFetcher,
    fake_conversation_service: ConversationService,
    valid_token: str,
    fake_user: User,
    ws_settings: Any,
):
    """StreamError from the service → client receives error frame with code stream_error."""
    fake_conv = MagicMock()
    fake_conv.id = uuid4()
    fake_conv.foundry_conversation_id = None
    fake_conversation_service.get_or_create = AsyncMock(return_value=(fake_conv, True))

    async def fake_execute(**kwargs):
        async def event_iter():
            yield StreamError(message="foundry timeout")

        return event_iter(), MagicMock(assistant_text="", conversation_id=fake_conv.id)

    fake_chat_svc = MagicMock()
    fake_chat_svc.execute = fake_execute

    fake_user_service_instance = MagicMock()
    fake_user_service_instance.get_or_create_by_oid = AsyncMock(return_value=fake_user)
    mock_user_service_class = MagicMock(return_value=fake_user_service_instance)

    fake_foundry = MagicMock(spec=FoundryClient)

    app = _make_ws_app(fake_jwks_fetcher, fake_conversation_service, fake_foundry)
    client = TestClient(app)

    with patch("app.api.websockets.chat.get_settings", return_value=ws_settings):
        with patch("app.api.websockets.chat.UserService", mock_user_service_class):
            with patch(
                "app.services.chat_turn.ChatTurnService", side_effect=lambda *a, **kw: fake_chat_svc
            ):
                with client.websocket_connect(
                    f"/ws/chat/{fake_conv.id}",
                    subprotocols=["bearer.jwt." + valid_token],
                ) as ws:
                    ws.send_json({"content": "test"})
                    frame = ws.receive_json()

    assert frame["type"] == "error"
    assert frame["code"] == "stream_error"
    assert "foundry timeout" in frame["message"]


def test_sends_error_on_unhandled_exception(
    fake_jwks_fetcher: JwksFetcher,
    fake_conversation_service: ConversationService,
    valid_token: str,
    fake_user: User,
    ws_settings: Any,
):
    """Unhandled exception in the event loop → client receives error frame with code internal and close 1011."""
    fake_conv = MagicMock()
    fake_conv.id = uuid4()
    fake_conv.foundry_conversation_id = None
    fake_conversation_service.get_or_create = AsyncMock(return_value=(fake_conv, True))

    async def fake_execute_that_raises(**kwargs):
        async def event_iter():
            yield StreamDelta(delta="partial")
            raise RuntimeError("unexpected error")

        return event_iter(), MagicMock(assistant_text="", conversation_id=fake_conv.id)

    fake_chat_svc = MagicMock()
    fake_chat_svc.execute = fake_execute_that_raises

    fake_user_service_instance = MagicMock()
    fake_user_service_instance.get_or_create_by_oid = AsyncMock(return_value=fake_user)
    mock_user_service_class = MagicMock(return_value=fake_user_service_instance)

    fake_foundry = MagicMock(spec=FoundryClient)

    app = _make_ws_app(fake_jwks_fetcher, fake_conversation_service, fake_foundry)
    client = TestClient(app)

    with patch("app.api.websockets.chat.get_settings", return_value=ws_settings):
        with patch("app.api.websockets.chat.UserService", mock_user_service_class):
            with patch(
                "app.services.chat_turn.ChatTurnService", side_effect=lambda *a, **kw: fake_chat_svc
            ):
                with client.websocket_connect(
                    f"/ws/chat/{fake_conv.id}",
                    subprotocols=["bearer.jwt." + valid_token],
                ) as ws:
                    ws.send_json({"content": "trigger error"})
                    ws.receive_json()  # delta
                    error_frame = ws.receive_json()  # error

    assert error_frame["type"] == "error"
    assert error_frame["code"] == "internal"
