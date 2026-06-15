# Authentication & Authorization Specification

## Purpose
Defines how the FastAPI backend validates Entra ID access tokens for REST and WebSocket requests, upserts the `users` row, and caches the Entra JWKS. The frontend uses MSAL React; the backend never sees passwords or refresh tokens.

## Requirements

### Requirement: Entra ID JWT validation
The system MUST validate every inbound access token against the Entra tenant's JWKS, checking `iss`, `aud`, `exp`, and signature. Failures MUST be rejected.

#### Scenario: Valid token
- GIVEN a token whose `iss`, `aud`, `exp`, and signature all match the cached JWKS
- WHEN the request reaches a protected handler
- THEN the user is resolved and the request proceeds.

#### Scenario: Expired or bad-signature token
- GIVEN a token past `exp` or signed by a key not in the JWKS
- WHEN validation runs
- THEN the response is `401` with a stable English `code` and a Spanish `message`.

### Requirement: JWKS fetch and cache
The system MUST fetch the JWKS on first use, cache in process memory with a TTL, and refresh on unknown `kid` or TTL expiry. Unreachable JWKS MUST retry with exponential backoff.

#### Scenario: Cold start
- GIVEN an empty cache
- WHEN the first valid token arrives
- THEN the backend fetches JWKS over HTTPS, caches it, and validates.

#### Scenario: Unknown `kid`
- GIVEN a token whose `kid` is not in the cache
- WHEN validation runs
- THEN the backend forces a JWKS refresh and re-validates.

### Requirement: User upsert on first auth
On the first successful validation for a given `oid`, the system MUST create a `users` row (UUID v4 PK) with `entraid_oid` set. Subsequent validations MUST NOT create duplicates.

#### Scenario: New OID
- GIVEN no `users.entraid_oid = "abc"`
- WHEN a token with `oid = "abc"` validates
- THEN a new user is inserted with a fresh UUID v4 `id` and `entraid_oid = "abc"`.

#### Scenario: Returning OID
- GIVEN a matching row exists
- WHEN the token validates
- THEN no insert happens and the existing row is returned.

### Requirement: WebSocket auth via subprotocol
The system MUST accept the access token only via the `Sec-WebSocket-Protocol` subprotocol. Tokens in the URL query string, cookies, or any other header MUST be rejected.

#### Scenario: Token in subprotocol
- GIVEN a client opens `/ws/chat` with `Sec-WebSocket-Protocol: bearer.jwt.<token>`
- WHEN the backend accepts
- THEN it extracts the token from the selected subprotocol, validates, and completes the upgrade.

#### Scenario: Token in query string or missing
- GIVEN a client opens `/ws/chat?token=<jwt>` or with no subprotocol
- WHEN the handshake reaches the backend
- THEN the connection is closed with `1008` and the token in the URL is ignored and never logged.

### Requirement: Spanish user-facing auth errors
Authentication failures MUST include a Spanish, neutral-professional `message` field. The machine `code` field MUST remain a stable English identifier.
