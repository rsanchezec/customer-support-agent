"""WebSocket endpoint for real-time chat streaming."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.api.auth.deps import decode_and_validate_token, get_claims_subject_key
from app.api.auth.jwks_fetcher import JwksFetcher
from app.domain.user import User
from app.services.conversation_service import ConversationService
from app.services.stream_events import StreamDelta, StreamError, StreamFinal
from app.services.text_sanitizer import clean_agent_text
from app.services.user_service import UserService
from app.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_CONTENT_LENGTH = 8000


def get_settings() -> Settings:
    """Return the module-level Settings instance."""
    return Settings()


async def authenticate_ws(
    token: str,
    jwks_fetcher: JwksFetcher,
    user_service: UserService,
) -> User:
    """Validate a JWT and return the corresponding user for WebSockets."""
    settings = get_settings()
    try:
        claims = await decode_and_validate_token(token, jwks_fetcher, settings)
    except HTTPException as exc:
        raise ValueError(str(exc.detail))

    oid = get_claims_subject_key(claims, settings)
    if not oid:
        raise ValueError("invalid token")

    email: str | None = claims.get("email") or claims.get("preferred_username")
    if isinstance(email, str) and not email:
        email = None

    return await user_service.get_or_create_by_oid(oid=oid, email=email)


def _extract_ws_token(raw_protocols: str) -> tuple[str | None, str | None]:
    """Extract bearer token and selected subprotocol from WS subprotocols."""
    token: str | None = None
    selected_subprotocol: str | None = None

    for proto in raw_protocols.split(","):
        proto = proto.strip()
        if proto == "bearer.jwt":
            selected_subprotocol = "bearer.jwt"
        elif proto.startswith("jwt."):
            token = proto[len("jwt.") :]
        elif proto.startswith("bearer.jwt."):
            token = proto[len("bearer.jwt.") :]
            selected_subprotocol = selected_subprotocol or proto
            break

    return token, selected_subprotocol


async def _send_bad_request_and_close(
    websocket: WebSocket,
    *,
    message: str,
    reason: str,
) -> None:
    """Send a bad_request frame and close the WebSocket."""
    await websocket.send_json(
        {
            "type": "error",
            "code": "bad_request",
            "message": message,
        }
    )
    await websocket.close(code=1008, reason=reason)


@router.websocket("/ws/chat/{conversation_id}")
async def ws_chat(
    websocket: WebSocket,
    conversation_id: uuid.UUID,
) -> None:
    """Stream chat turns over one persistent WebSocket connection."""
    raw_protocols = websocket.headers.get("sec-websocket-protocol", "")
    logger.warning(
        "[CHAT DEBUG] ws_start conversation_id=%s protocol_count=%s",
        conversation_id,
        len([proto for proto in raw_protocols.split(",") if proto.strip()]),
    )

    token, selected_subprotocol = _extract_ws_token(raw_protocols)
    if not token or not selected_subprotocol:
        logger.warning(
            "[CHAT DEBUG] ws_missing_subprotocol conversation_id=%s",
            conversation_id,
        )
        await websocket.close(code=1008, reason="missing subprotocol")
        return

    logger.warning(
        "[CHAT DEBUG] ws_subprotocol_ok conversation_id=%s selected=%s token_len=%s",
        conversation_id,
        selected_subprotocol,
        len(token),
    )

    jwks_fetcher: JwksFetcher = websocket.app.state.jwks_fetcher

    from app.db.session import _get_session_factory

    session_factory = _get_session_factory()
    user_service = UserService(session_factory=session_factory)

    try:
        user = await authenticate_ws(token, jwks_fetcher, user_service)
    except ValueError as exc:
        logger.warning(
            "[CHAT DEBUG] ws_auth_failed reason=%s conversation_id=%s",
            str(exc),
            conversation_id,
        )
        await websocket.close(code=1008, reason=str(exc))
        return

    logger.warning(
        "[CHAT DEBUG] ws_auth_ok conversation_id=%s user_id=%s",
        conversation_id,
        user.id,
    )

    await websocket.accept(subprotocol=selected_subprotocol)
    logger.warning("[CHAT DEBUG] ws_accepted conversation_id=%s", conversation_id)

    conv_service: ConversationService = websocket.app.state.conversation_service
    conv, created = await conv_service.get_or_create(
        user=user,
        conversation_id=conversation_id,
    )
    logger.warning(
        "[CHAT DEBUG] conversation_ready conversation_id=%s created=%s foundry_session=%s",
        conv.id,
        created,
        "yes" if conv.foundry_conversation_id else "no",
    )

    foundry_client = websocket.app.state.foundry_client

    from app.services.chat_turn import ChatTurnService

    while True:
        try:
            payload = await websocket.receive_json()
        except WebSocketDisconnect:
            logger.warning(
                "[CHAT DEBUG] ws_client_disconnected conversation_id=%s",
                conversation_id,
            )
            return
        except Exception as exc:
            logger.warning(
                "[CHAT DEBUG] ws_invalid_message_format conversation_id=%s error=%s",
                conversation_id,
                str(exc),
            )
            await websocket.close(code=1008, reason="invalid message format")
            return

        content: str | None = payload.get("content") if isinstance(payload, dict) else None
        logger.warning(
            "[CHAT DEBUG] ws_message_received conversation_id=%s payload_type=%s content_len=%s",
            conversation_id,
            type(payload).__name__,
            len(content) if isinstance(content, str) else None,
        )

        if not isinstance(content, str) or not content:
            logger.warning("[CHAT DEBUG] ws_bad_content conversation_id=%s", conversation_id)
            await _send_bad_request_and_close(
                websocket,
                message="content must be a non-empty string",
                reason="invalid content",
            )
            return

        if len(content) > MAX_CONTENT_LENGTH:
            logger.warning(
                "[CHAT DEBUG] ws_content_too_long conversation_id=%s content_len=%s",
                conversation_id,
                len(content),
            )
            await _send_bad_request_and_close(
                websocket,
                message=f"content exceeds maximum length of {MAX_CONTENT_LENGTH}",
                reason="content too long",
            )
            return

        async with session_factory() as session:
            chat_svc = ChatTurnService(
                session=session,
                foundry_client=foundry_client,
                conversation=conv,
            )

            logger.warning(
                "[CHAT DEBUG] chat_turn_execute_start conversation_id=%s",
                conv.id,
            )
            events_iter, _result = await chat_svc.execute(
                user=user,
                user_message=content,
            )
            logger.warning(
                "[CHAT DEBUG] chat_turn_execute_ready conversation_id=%s",
                conv.id,
            )

            try:
                assistant_text = ""
                async for event in events_iter:
                    if isinstance(event, StreamDelta):
                        assistant_text += event.delta
                        logger.warning(
                            "[CHAT DEBUG] stream_delta conversation_id=%s len=%s",
                            conv.id,
                            len(event.delta),
                        )
                        await websocket.send_json({"type": "delta", "text": event.delta})
                    elif isinstance(event, StreamFinal):
                        assistant_text = clean_agent_text(event.text or assistant_text)
                        logger.warning(
                            "[CHAT DEBUG] stream_final conversation_id=%s len=%s",
                            conv.id,
                            len(assistant_text),
                        )
                        await websocket.send_json(
                            {
                                "type": "done",
                                "conversation_id": str(conv.id),
                                "foundry_conversation_id": conv.foundry_conversation_id or "",
                                "text": assistant_text,
                            }
                        )

                        logger.warning(
                            "[CHAT DEBUG] assistant_persist_start conversation_id=%s",
                            conv.id,
                        )
                        await chat_svc.persist_assistant_message(
                            conversation_id=conv.id,
                            assistant_text=assistant_text,
                        )
                        logger.warning(
                            "[CHAT DEBUG] assistant_persist_done conversation_id=%s",
                            conv.id,
                        )
                        break
                    elif isinstance(event, StreamError):
                        logger.warning(
                            "[CHAT DEBUG] stream_error conversation_id=%s message=%s",
                            conv.id,
                            event.message,
                        )
                        await websocket.send_json(
                            {
                                "type": "error",
                                "code": "stream_error",
                                "message": event.message,
                            }
                        )
                        break
            except WebSocketDisconnect:
                logger.warning(
                    "[CHAT DEBUG] ws_client_disconnected conversation_id=%s",
                    conversation_id,
                )
                return
            except Exception as exc:
                logger.error(
                    "[CHAT DEBUG] ws_unhandled_error error=%s conversation_id=%s",
                    str(exc),
                    conversation_id,
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
