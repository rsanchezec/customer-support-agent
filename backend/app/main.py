"""FastAPI application factory and lifespan."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth.jwks_fetcher import JwksFetcher
from app.api.health import router as health_router
from app.settings import Settings


def _build_jwks_uri(settings: Settings) -> str:
    """Construct the Entra ID JWKS URI from the tenant ID."""
    return f"https://login.microsoftonline.com/{settings.entra_tenant_id}/discovery/v2.0/keys"


def create_app(settings: Settings) -> FastAPI:
    """Build and configure the FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: create JwksFetcher and attach to app state
        jwks_uri = _build_jwks_uri(settings)
        app.state.jwks_fetcher = JwksFetcher(jwks_uri=jwks_uri)
        yield
        # Shutdown: close the JwksFetcher's HTTP client
        await app.state.jwks_fetcher.aclose()

    app = FastAPI(
        title="customer-support-agent",
        version=settings.agent_version_str,
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

    return app


# Module-level app instance for `uvicorn app.main:app`
settings = Settings()
app = create_app(settings)
