"""FastAPI authentication dependencies."""

from __future__ import annotations

import logging
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request
from jwt import PyJWK

from app.api.auth.jwks_fetcher import JwksFetcher
from app.domain.user import User
from app.services.conversation_service import ConversationService
from app.services.user_service import UserService
from app.settings import Settings

logger = logging.getLogger(__name__)


def get_settings() -> Settings:
    """Return the module-level Settings instance."""
    return Settings()


def _build_jwks_uri(settings: Settings) -> str:
    """Construct the Entra ID JWKS URI from the tenant ID."""
    tenant = settings.entra_effective_jwks_tenant_id
    return f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"


def _build_jwks_v1_uri(settings: Settings) -> str:
    """Construct the Entra ID v1 JWKS URI from the tenant ID."""
    return f"https://login.microsoftonline.com/{settings.entra_tenant_id}/discovery/keys"


def _accepted_audiences(settings: Settings) -> list[str]:
    """Return the accepted token audiences for this API."""
    audiences = [
        settings.entra_app_audience,
        *settings.entra_allowed_audiences,
    ]
    if settings.entra_client_id:
        audiences.extend(
            [
                settings.entra_client_id,
                f"api://{settings.entra_client_id}",
            ]
        )
    return list(dict.fromkeys(aud for aud in audiences if aud))


def _accepted_issuers(settings: Settings) -> list[str]:
    """Return accepted Entra issuer formats for v1 and v2 access tokens."""
    issuers = [*settings.entra_allowed_issuers]
    if settings.entra_tenant_id:
        issuers.extend(
            [
                f"https://sts.windows.net/{settings.entra_tenant_id}/",
                f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
            ]
        )
    return list(dict.fromkeys(iss for iss in issuers if iss))


def _issuer_matches_tenant(issuer: str, tenant_id: str) -> bool:
    """Return whether an issuer is a valid v1/v2 Entra issuer for a tenant."""
    return issuer in {
        f"https://sts.windows.net/{tenant_id}/",
        f"https://login.microsoftonline.com/{tenant_id}/v2.0",
    }


def _is_accepted_issuer(claims: dict, settings: Settings) -> bool:
    """Validate issuer for single-tenant or public multi-tenant demos."""
    issuer = claims.get("iss")
    if not isinstance(issuer, str) or not issuer:
        return False

    if issuer in _accepted_issuers(settings):
        return True

    if not settings.entra_allow_multitenant_issuers:
        return False

    tenant_id = claims.get("tid")
    return isinstance(tenant_id, str) and _issuer_matches_tenant(issuer, tenant_id)


def get_claims_subject_key(claims: dict, settings: Settings) -> str | None:
    """Return the stable user key stored in users.entraid_oid."""
    subject = claims.get("oid") or claims.get("sub")
    if not isinstance(subject, str) or not subject:
        return None

    tenant_id = claims.get("tid")
    if settings.entra_allow_multitenant_issuers and isinstance(tenant_id, str) and tenant_id:
        return f"{tenant_id}:{subject}"

    return subject


def _log_invalid_token(reason: str, token: str, settings: Settings, kid: str | None) -> None:
    """Log non-sensitive token metadata to diagnose local auth configuration."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        claims = {}

    logger.warning(
        "auth token rejected reason=%s kid=%s aud=%s iss=%s ver=%s scp=%s expected_aud=%s",
        reason,
        kid,
        claims.get("aud"),
        claims.get("iss"),
        claims.get("ver"),
        claims.get("scp"),
        _accepted_audiences(settings),
    )


async def decode_and_validate_token(
    token: str,
    jwks: JwksFetcher,
    settings: Settings,
) -> dict:
    """Validate an Entra access token and return its claims.

    The frontend should request the API scope, but Entra can still issue v1 or
    v2 access tokens depending on the app manifest. We validate with the
    configured JWKS first and only fall back to alternate tenant JWKS endpoints
    if the signing key requires it.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        _log_invalid_token("bad_header", token, settings, None)
        raise HTTPException(status_code=401, detail="invalid token")

    kid: str | None = unverified_header.get("kid")
    if not kid:
        _log_invalid_token("missing_kid", token, settings, None)
        raise HTTPException(status_code=401, detail="invalid token")

    decode_kwargs: dict = {"algorithms": ["RS256"]}
    audiences = _accepted_audiences(settings)
    issuers = _accepted_issuers(settings)
    if audiences:
        decode_kwargs["audience"] = audiences
    if issuers and not settings.entra_allow_multitenant_issuers:
        decode_kwargs["issuer"] = issuers

    saw_matching_kid = False
    saw_signature_error = False

    def try_decode_with_keys(jwks_keys: dict) -> dict | None:
        nonlocal saw_matching_kid, saw_signature_error

        for key in jwks_keys.get("keys", []):
            if key.get("kid") != kid:
                continue

            saw_matching_kid = True
            try:
                pyjwk = PyJWK.from_dict(key)
                claims = jwt.decode(token, pyjwk.key, **decode_kwargs)
                if not _is_accepted_issuer(claims, settings):
                    _log_invalid_token("invalid_issuer", token, settings, kid)
                    raise HTTPException(status_code=401, detail="invalid token")
                return claims
            except jwt.ExpiredSignatureError:
                _log_invalid_token("expired", token, settings, kid)
                raise HTTPException(status_code=401, detail="token expired")
            except jwt.InvalidSignatureError:
                saw_signature_error = True
                continue
            except jwt.PyJWTError as exc:
                _log_invalid_token(type(exc).__name__, token, settings, kid)
                raise HTTPException(status_code=401, detail="invalid token")
            except HTTPException:
                raise
            except Exception:
                _log_invalid_token("invalid_jwk", token, settings, kid)
                raise HTTPException(status_code=401, detail="invalid token")

        return None

    try:
        configured_keys = await jwks.get_keys()
    except Exception as exc:
        logger.warning(
            "auth jwks fetch failed label=configured error=%s",
            type(exc).__name__,
        )
        _log_invalid_token("jwks_fetch_failed", token, settings, kid)
        raise HTTPException(status_code=401, detail="invalid token")

    claims = try_decode_with_keys(configured_keys)
    if claims is not None:
        return claims

    configured_uri = getattr(jwks, "_jwks_uri", "")
    for label, uri in (
        ("v2", _build_jwks_uri(settings)),
        ("v1", _build_jwks_v1_uri(settings)),
    ):
        if uri == configured_uri:
            continue

        try:
            alternate_keys = await JwksFetcher(jwks_uri=uri).get_keys()
        except Exception as exc:
            logger.warning(
                "auth jwks fetch failed label=%s error=%s",
                label,
                type(exc).__name__,
            )
            continue

        claims = try_decode_with_keys(alternate_keys)
        if claims is not None:
            return claims

    reason = "invalid_signature" if saw_signature_error else "unknown_kid"
    if not saw_matching_kid:
        reason = "unknown_kid"
    _log_invalid_token(reason, token, settings, kid)
    raise HTTPException(status_code=401, detail="invalid token")


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


def get_conversation_service(
    request: Request,
) -> ConversationService:
    """Build a ConversationService from the request's session factory."""
    from app.db.session import _get_session_factory

    factory = _get_session_factory()
    return ConversationService(session_factory=factory)


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

    claims = await decode_and_validate_token(token, jwks, settings)

    oid = get_claims_subject_key(claims, settings)
    if not oid:
        raise HTTPException(status_code=401, detail="invalid token")

    email: str | None = claims.get("email") or claims.get("preferred_username")
    if isinstance(email, str) and not email:
        email = None

    return await user_service.get_or_create_by_oid(oid=oid, email=email)
