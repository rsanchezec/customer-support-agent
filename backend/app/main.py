"""FastAPI application factory and lifespan."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.settings import Settings


def create_app(settings: Settings) -> FastAPI:
    """Build and configure the FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: nothing yet (Foundry client added in slice 6)
        yield
        # Shutdown: nothing yet

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
