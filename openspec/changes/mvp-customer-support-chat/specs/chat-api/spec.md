# Chat API Specification

## Purpose
Defines the FastAPI REST endpoints and the `/ws/chat` WebSocket endpoint the React client uses to manage conversations and stream assistant tokens. Covers handshake, message envelope, outgoing frames, error codes, and CORS.

## Requirements

### Requirement: REST conversation lifecycle
The system MUST expose `POST /conversations` and `GET /conversations/{id}/messages`. Both MUST require a valid Entra token and MUST scope reads and writes to the authenticated user.

#### Scenario: Create
- GIVEN an authenticated user
- WHEN `POST /conversations` is called
- THEN the response is `201` with `{"id": "<uuid4>"}` and the new row is owned by the caller.

#### Scenario: List messages
- GIVEN user A owns `c-uuid` with N messages
- WHEN `GET /conversations/c-uuid/messages` is called by A
- THEN the response is `200` with `{"messages": [...]}` in chronological order.

#### Scenario: Cross-user access
- GIVEN `c-uuid` belongs to user B
- WHEN user A calls `GET /conversations/c-uuid/messages`
- THEN the response is `404` (not 403, to avoid existence leak).

#### Scenario: Missing or invalid token
- GIVEN a request with no `Authorization` or a bad token
- WHEN it reaches a protected handler
- THEN the response is `401`.

### Requirement: WebSocket endpoint at `/ws/chat`
The endpoint MUST authenticate via the `Sec-WebSocket-Protocol` subprotocol (see `auth` spec) and MUST scope the session to the authenticated user.

#### Scenario: Successful handshake
- GIVEN a client opens `/ws/chat` with `Sec-WebSocket-Protocol: bearer.<jwt>`
- WHEN the backend accepts
- THEN the response's `Sec-WebSocket-Protocol` echoes `bearer.<jwt>` and the connection enters "ready".

#### Scenario: Auth failure
- GIVEN a client opens without a valid subprotocol
- WHEN the handshake runs
- THEN the connection is closed with `1008` and reason "unauthenticated".

### Requirement: Inbound message envelope
The backend MUST accept `{"type": "user_message", "content": "<text>", "conversation_id": "<uuid4|null>"}`. Unknown `type` values MUST trigger an `error` frame; the connection MUST stay open.

#### Scenario: User sends a message
- GIVEN a "ready" WS
- WHEN the client sends a valid `user_message`
- THEN the backend persists the user message and triggers a Foundry run.

#### Scenario: Empty or oversized content
- GIVEN `content` is empty or exceeds the configured limit (default 4000 chars)
- WHEN the frame arrives
- THEN the backend replies `error.code = "empty_message"` or `"message_too_long"` and does NOT call Foundry.

#### Scenario: Conversation not owned
- GIVEN `conversation_id` belongs to a different user
- WHEN the frame arrives
- THEN the backend replies `error.code = "conversation_not_found"` and keeps the connection open.

### Requirement: Outbound frame types
The backend MUST emit: `assistant_delta` (text chunk), `assistant_done` (final text + ids), `error` (recoverable), `close` (terminal). Per-token persistence is forbidden.

#### Scenario: Streaming response
- GIVEN 5 deltas
- WHEN each arrives
- THEN the backend forwards exactly one `assistant_delta` per non-empty update; persistence is NOT touched between deltas.

#### Scenario: Stream completion
- GIVEN a completed run
- WHEN the final text is available
- THEN the backend emits `assistant_done` with the full text and a `message_id`, and persists exactly one `assistant` row.

#### Scenario: Recoverable error
- GIVEN a transient Foundry error (429, 5xx, timeout)
- WHEN caught
- THEN the backend emits `error.code = "foundry_transient"` and keeps the connection open.

### Requirement: WebSocket close codes
The backend MUST use `1008` for auth/policy violations and `1011` for server errors. `1006` MUST NOT be sent as a code by the backend.

#### Scenario: Unhandled server error mid-stream
- GIVEN an unhandled exception
- WHEN the backend cannot recover
- THEN it emits a final `error` frame and closes with `1011`.

### Requirement: CORS and Spanish user-facing errors
`CORS_ALLOWED_ORIGINS` MUST be configurable (dev MAY be `*`; prod MUST be a finite HTTPS list). Every `error` frame and user-facing `4xx/5xx` body MUST include a neutral-professional-Spanish `message`; the `code` field MUST remain a stable English identifier.
