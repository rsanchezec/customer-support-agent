"""FastAPI application factory and lifespan."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth.jwks_fetcher import JwksFetcher
from app.api.health import router as health_router
from app.api.rest.conversations import router as conversations_router
from app.api.websockets.chat import router as chat_ws_router
from app.db.session import _get_session_factory
from app.services.conversation_service import ConversationService
from app.services.foundry import FoundryClient
from app.settings import Settings


def _build_jwks_uri(settings: Settings) -> str:
    """Construct the Entra ID JWKS URI from the tenant ID."""
    return f"https://login.microsoftonline.com/{settings.entra_tenant_id}/discovery/v2.0/keys"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    if settings is None:
        settings = Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: create JwksFetcher and attach to app state
        jwks_uri = _build_jwks_uri(settings)
        app.state.jwks_fetcher = JwksFetcher(jwks_uri=jwks_uri)

        # Startup: create FoundryClient and attach to app state
        app.state.foundry_client = FoundryClient(
            endpoint=settings.foundry_project_endpoint,
            agent_name=settings.azure_ai_agent_name,
            agent_version=settings.agent_version_str,
        )

        # Startup: create ConversationService and attach to app state
        app.state.conversation_service = ConversationService(
            session_factory=_get_session_factory(),
        )

        yield

        # Shutdown: close the JwksFetcher's HTTP client
        await app.state.jwks_fetcher.aclose()

        # Shutdown: close the Foundry client
        await app.state.foundry_client.aclose()

    app = FastAPI(
        title="customer-support-agent",
        version=settings.agent_version_str or "dev",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, tags=["health"])
    app.include_router(conversations_router, tags=["conversations"])
    app.include_router(chat_ws_router, tags=["websockets"])

    return app


# Module-level app instance for `uvicorn app.main:app`
settings = Settings()
app = create_app(settings)
