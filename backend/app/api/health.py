"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe — returns 200 when the app is running."""
    return {"status": "ok"}
