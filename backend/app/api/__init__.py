"""API package — re-exports public auth dependencies and routers."""

from app.api.auth.deps import get_conversation_service, get_current_user
from app.api.auth.jwks_fetcher import JwksFetcher
from app.api.rest.conversations import router as conversations_router
from app.api.websockets.chat import router as chat_ws_router
from app.services.user_service import UserService

__all__ = [
    "chat_ws_router",
    "conversations_router",
    "get_conversation_service",
    "get_current_user",
    "JwksFetcher",
    "UserService",
]
