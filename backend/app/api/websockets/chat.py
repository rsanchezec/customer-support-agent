"""WebSocket endpoint for real-time chat streaming.

Route: WS /ws/chat/{conversation_id}

Auth
----
The JWT is carried inside the ``Sec-WebSocket-Protocol`` header as
``bearer.jwt.<token>``.  This is the ONLY authorised transport; tokens
in query strings or custom headers are rejected with close code 1008.

Message envelope (client → server)
----------------------------------
First frame after handshake::

    {"content": "...", "metadata": {...} | null}

Outbound frames (server → client)
---------------------------------
``delta``   — partial token chunk from the agent stream.
``done``   — stream finished; includes conversation identifiers.
``error``  — non-recoverable error; connection closed afterwards.
"""

from __future__ import annotations

import logging
import uuid

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jwt import PyJWK

from app.api.auth.jwks_fetcher import JwksFetcher
from app.domain.user import User
from app.services.conversation_service import ConversationService
from app.services.stream_events import StreamDelta, StreamError, StreamFinal
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter()

# Maximum allowed content length per user message.
MAX_CONTENT_LENGTH = 8000


# ---------------------------------------------------------------------------
# Authentication helper (WebSocket variant of get_current_user)
# ---------------------------------------------------------------------------


async def authenticate_ws(
    token: str,
    jwks_fetcher: JwksFetcher,
    user_service: UserService,
) -> User:
    """Validate a JWT and return the corresponding User (WS variant).

    Performs the same RS256/aud/iss/exp validation as ``get_current_user``
    but reads from the ``Sec-WebSocket-Protocol`` subprotocol instead of an
    HTTP header.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise ValueError("invalid token")

    kid: str | None = unverified_header.get("kid")
    if not kid:
        raise ValueError("invalid token")

    jwks_keys = await jwks_fetcher.get_keys()
    jwk_dict: dict | None = None
    for key in jwks_keys.get("keys", []):
        if key.get("kid") == kid:
            jwk_dict = key
            break

    if jwk_dict is None:
        raise ValueError("unknown kid")

    try:
        pyjwk = PyJWK.from_dict(jwk_dict)
    except Exception:
        raise ValueError("invalid token")

    # Import Settings lazily to avoid circular imports.
    from app.settings import Settings

    settings = Settings()

    try:
        claims = jwt.decode(
            token,
            pyjwk.key,
            algorithms=["RS256"],
            audience=settings.entra_app_audience,
            issuer=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("token expired")
    except jwt.PyJWTError:
        raise ValueError("invalid token")

    oid = claims.get("oid")
    if not oid:
        raise ValueError("invalid token")

    email: str | None = claims.get("email") or claims.get("preferred_username")
    if isinstance(email, str) and not email:
        email = None

    return await user_service.get_or_create_by_oid(oid=oid, email=email)


# ---------------------------------------------------------------------------
# WebSocket router
# ---------------------------------------------------------------------------


@router.websocket("/ws/chat/{conversation_id}")
async def ws_chat(
    websocket: WebSocket,
    conversation_id: uuid.UUID,
) -> None:
    """Real-time chat streaming endpoint.

    Parameters
    ----------
    websocket
        The live WebSocket connection.
    conversation_id
        The conversation UUID from the URL path.  ``None`` is not allowed
        by the route definition; this parameter exists purely for type
        narrowing.
    """
    # -----------------------------------------------------------------------
    # 1. Subprotocol negotiation
    # -----------------------------------------------------------------------
    raw_protocols = websocket.headers.get("sec-websocket-protocol", "")

    # Client sends "bearer.jwt.<token>" or "bearer.jwt.<token>, chat.v1"
    # We look for the first subprotocol that starts with "bearer.jwt.".
    token: str | None = None
    for proto in raw_protocols.split(","):
        proto = proto.strip()
        if proto.startswith("bearer.jwt."):
            token = proto[len("bearer.jwt.") :]
            break

    if not token:
        logger.warning("ws_chat missing_subprotocol conversation_id=%s", conversation_id)
        await websocket.close(code=1008, reason="missing subprotocol")
        return

    # -----------------------------------------------------------------------
    # 2. JWT validation
    # -----------------------------------------------------------------------
    jwks_fetcher: JwksFetcher = websocket.app.state.jwks_fetcher

    # Build a UserService on the fly — the lifespan does not own one.
    from app.db.session import _get_session_factory

    factory = _get_session_factory()
    user_service = UserService(session_factory=factory)

    try:
        user = await authenticate_ws(token, jwks_fetcher, user_service)
    except ValueError as exc:
        logger.warning(
            "ws_chat auth_failed reason=%s conversation_id=%s", str(exc), conversation_id
        )
        await websocket.close(code=1008, reason=str(exc))
        return

    # -----------------------------------------------------------------------
    # 3. Accept the WebSocket (echo the accepted subprotocol)
    # -----------------------------------------------------------------------
    await websocket.accept(subprotocol="bearer.jwt")

    # -----------------------------------------------------------------------
    # 4. Receive first message — user content
    # -----------------------------------------------------------------------
    try:
        payload = await websocket.receive_json()
    except Exception:
        await websocket.close(code=1008, reason="invalid message format")
        return

    content: str | None = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(content, str) or not content:
        await websocket.send_json(
            {
                "type": "error",
                "code": "bad_request",
                "message": "content must be a non-empty string",
            }
        )
        await websocket.close(code=1008, reason="invalid content")
        return

    if len(content) > MAX_CONTENT_LENGTH:
        await websocket.send_json(
            {
                "type": "error",
                "code": "bad_request",
                "message": f"content exceeds maximum length of {MAX_CONTENT_LENGTH}",
            }
        )
        await websocket.close(code=1008, reason="content too long")
        return

    # -----------------------------------------------------------------------
    # 5. Resolve conversation
    # -----------------------------------------------------------------------
    conv_service: ConversationService = websocket.app.state.conversation_service
    conv, _created = await conv_service.get_or_create(
        user=user,
        conversation_id=conversation_id,
    )

    # -----------------------------------------------------------------------
    # 6. Stream events to client
    # -----------------------------------------------------------------------
    foundry_client = websocket.app.state.foundry_client

    # Get a session for ChatTurnService.
    from app.db.session import _get_session_factory

    session_factory = _get_session_factory()
    async with session_factory() as session:
        from app.services.chat_turn import ChatTurnService

        chat_svc = ChatTurnService(
            session=session,
            foundry_client=foundry_client,
            conversation=conv,
        )

        events_iter, _result = await chat_svc.execute(
            user=user,
            user_message=content,
        )

        try:
            async for event in events_iter:
                if isinstance(event, StreamDelta):
                    await websocket.send_json(
                        {
                            "type": "delta",
                            "text": event.delta,
                        }
                    )
                elif isinstance(event, StreamFinal):
                    await websocket.send_json(
                        {
                            "type": "done",
                            "conversation_id": str(conv.id),
                            "foundry_conversation_id": conv.foundry_conversation_id or "",
                        }
                    )
                    # Persist the assistant message on stream completion.
                    await chat_svc.persist_assistant_message(
                        conversation_id=conv.id,
                        assistant_text=event.text,
                    )
                    break
                elif isinstance(event, StreamError):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "code": "stream_error",
                            "message": event.message,
                        }
                    )
                    break
        except WebSocketDisconnect:
            # Client disconnected mid-stream — ChatTurnService already
            # committed the user message; no assistant row is persisted.
            logger.info("ws_chat client_disconnected conversation_id=%s", conversation_id)
            return
        except Exception as exc:
            logger.error(
                "ws_chat unhandled_error error=%s conversation_id=%s", str(exc), conversation_id
            )
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "internal",
                    "message": "An internal error occurred.",
                }
            )
            await websocket.close(code=1011)
            return

    await websocket.close()
