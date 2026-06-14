"""FastAPI authentication dependencies."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request
from jwt import PyJWK

from app.api.auth.jwks_fetcher import JwksFetcher
from app.domain.user import User
from app.services.user_service import UserService
from app.settings import Settings


def get_settings() -> Settings:
    """Return the module-level Settings instance."""
    return Settings()


def _build_jwks_uri(settings: Settings) -> str:
    """Construct the Entra ID JWKS URI from the tenant ID."""
    return f"https://login.microsoftonline.com/{settings.entra_tenant_id}/discovery/v2.0/keys"


def get_jwks_fetcher(
    request: Request,
) -> JwksFetcher:
    """Return the JwksFetcher stored on app.state, creating one if absent."""
    if not hasattr(request.app.state, "jwks_fetcher"):
        settings = get_settings()
        jwks_uri = _build_jwks_uri(settings)
        request.app.state.jwks_fetcher = JwksFetcher(jwks_uri=jwks_uri)
    return request.app.state.jwks_fetcher


def get_user_service(
    request: Request,
) -> UserService:
    """Build a UserService from the request's session factory."""
    from app.db.session import _get_session_factory

    factory = _get_session_factory()
    return UserService(session_factory=factory)


async def get_current_user(
    authorization: Annotated[str, Header()],
    jwks: Annotated[JwksFetcher, Depends(get_jwks_fetcher)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> User:
    """Validate a bearer token and return the current User.

    Steps:
    1. Extract bearer token from ``Authorization: Bearer <token>``.
    2. Decode the JWT header to obtain the ``kid``.
    3. Look up the JWK by ``kid`` in the JWKS cache.
    4. Verify the token signature, audience, and issuer with PyJWT.
    5. Extract ``oid`` and ``email`` (or ``preferred_username``) from claims.
    6. Upsert the User row by OID and return it.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="missing or invalid authorization header",
        )

    token = authorization[len("Bearer ") :]
    settings = get_settings()

    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid token")

    kid: str | None = unverified_header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="invalid token")

    jwks_keys = await jwks.get_keys()
    jwk_dict: dict | None = None
    for key in jwks_keys.get("keys", []):
        if key.get("kid") == kid:
            jwk_dict = key
            break

    if jwk_dict is None:
        raise HTTPException(status_code=401, detail="unknown kid")

    try:
        pyjwk = PyJWK.from_dict(jwk_dict)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token")

    try:
        claims = jwt.decode(
            token,
            pyjwk.key,
            algorithms=["RS256"],
            audience=settings.entra_app_audience,
            issuer=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid token")

    oid = claims.get("oid")
    if not oid:
        raise HTTPException(status_code=401, detail="invalid token")

    email: str | None = claims.get("email") or claims.get("preferred_username")
    if isinstance(email, str) and not email:
        email = None

    return await user_service.get_or_create_by_oid(oid=oid, email=email)
