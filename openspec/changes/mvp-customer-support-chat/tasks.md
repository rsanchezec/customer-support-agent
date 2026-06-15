# Tasks: MVP Customer-Support Chat

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~2,080 total across 10 slices |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | 10 chained PRs, one per slice |
| Delivery strategy | force-chained |
| Chain strategy | TBD (orchestrator will ask user) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: TBD
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | BE bootstrap: uv + FastAPI app + config + healthz | PR 1 | Base = main; slice 1 only |
| 2a | BE DB layer (part 1): engine + models + session | PR 2a | Base = PR 1; ~190 lines |
| 2b | BE DB layer (part 2): Alembic + 0001_init migration | PR 2b | Base = PR 2a; ~190 lines |
| 3 | BE Entra JWT validation: JWKS + token + user upsert | PR 3 | Base = PR 2b; ~160 lines |
| 4 | BE repositories: users + conversations + messages | PR 4 | Base = PR 3; ~120 lines |
| 5 | BE REST endpoints: POST/GET conversations + messages | PR 5 | Base = PR 4; ~110 lines |
| 6 | BE WS + Foundry bridge: /ws/chat + streaming service | PR 6 | Base = PR 5; ~260 lines |
| 7 | BE tests: pytest + pytest-asyncio + all test files | PR 7 | Base = PR 6; ~220 lines |
| 8 | BE observability: structlog + error mapping | PR 8 | Base = PR 7; ~140 lines |
| 9 | FE bootstrap: Vite + React 19 + MSAL + Zustand stores | PR 9 | Base = PR 8; ~280 lines; parallel with 1–6 |
| 10 | FE Chat page + WS client + persistence hooks | PR 10 | Base = PR 9; ~320 lines |

---

## Slice 1: Backend Bootstrap (uv + FastAPI)

**Goal**: Establish the `backend/` project with `uv`, a minimal FastAPI app, pydantic-settings config, and a `/healthz` endpoint.

**Files**:
- `backend/pyproject.toml` (~40 lines) — uv project, ruff, pytest-asyncio, all BE deps
- `backend/uv.lock` (generated)
- `backend/.env` (~15 lines) — mirrors `example/.env` keys: `DATABASE_URL`, `FOUNDRY_*`, `ENTRA_*`, `CORS_ALLOWED_ORIGINS`
- `backend/.env.example` (~15 lines)
- `backend/app/__init__.py` (3 lines)
- `backend/app/main.py` (~40 lines) — FastAPI app, lifespan placeholder, include router
- `backend/app/config.py` (~30 lines) — pydantic-settings `Settings` reading env
- `backend/app/api/__init__.py` (3 lines)
- `backend/app/api/health.py` (~10 lines) — `GET /healthz → 200`
- `backend/README.md` (~20 lines) — quickstart: `uv run uvicorn`

**Tasks**:
- [x] 1.1 Create `backend/pyproject.toml` with all dependencies: fastapi, uvicorn, sqlalchemy[asyncio], aiosqlite, alembic, pyjwt[crypto], httpx, pydantic-settings, structlog, pytest, pytest-asyncio, ruff
- [x] 1.2 Create `backend/.env` mirroring `example/.env` keys with placeholder values
- [x] 1.3 Create `backend/.env.example` with all keys documented
- [x] 1.4 Create `backend/app/__init__.py`
- [x] 1.5 Create `backend/app/config.py` with pydantic-settings `Settings` class
- [x] 1.6 Create `backend/app/main.py` with FastAPI(), lifespan (placeholder), health router
- [x] 1.7 Create `backend/app/api/__init__.py`
- [x] 1.8 Create `backend/app/api/health.py` with `GET /healthz → 200`
- [x] 1.9 Run `uv sync` and verify `uv run uvicorn app.main:app --port 8000` boots
- [x] 1.10 Verify `GET http://localhost:8000/healthz` returns 200

**Depends on**: —
**Acceptance criteria**:
- `uv run uvicorn app.main:app` boots without import errors
- `GET /healthz` → 200 with JSON `{"status":"ok"}`
- `uv run ruff check .` passes
- `uv run ruff format --check .` passes

**Estimated changed lines**: ~90

---

## Slice 2a: DB Layer — Engine, Models, Session

**Goal**: Async SQLAlchemy 2.0 engine, typed declarative models for `users`, `conversations`, `messages`, and a per-request session dependency.

**Files**:
- `backend/app/infrastructure/__init__.py` (3 lines)
- `backend/app/infrastructure/db/__init__.py` (3 lines)
- `backend/app/infrastructure/db/engine.py` (~60 lines) — async engine, WAL PRAGMA listener, echo from env
- `backend/app/infrastructure/db/session.py` (~30 lines) — async_sessionmaker, `get_session` FastAPI dep
- `backend/app/infrastructure/db/models.py` (~70 lines) — Base, User, Conversation, Message with Uuid PKs
- `backend/app/domain/__init__.py` (3 lines)
- `backend/app/domain/entities.py` (~25 lines) — User, Conversation, Message dataclasses
- `backend/pytest.ini` (~10 lines) — asyncio_mode = auto

**Tasks**:
2a.1 Create `backend/app/infrastructure/__init__.py`
2a.2 Create `backend/app/infrastructure/db/__init__.py`
2a.3 Create `backend/app/infrastructure/db/engine.py` — `create_async_engine` from `DATABASE_URL`, WAL PRAGMA listener, `echo` from settings
2a.4 Create `backend/app/infrastructure/db/session.py` — `async_sessionmaker`, `get_session` dep yielding `AsyncSession`
2a.5 Create `backend/app/infrastructure/db/models.py` — Base, User (UUID PK, entraid_oid unique, email, display_name, last_seen_at, created_at), Conversation (FK user_id, foundry_conversation_id, title, created_at), Message (FK conversation_id, role, content Text, foundry_message_id, created_at)
2a.6 Create `backend/app/domain/__init__.py`
2a.7 Create `backend/app/domain/entities.py` — User, Conversation, Message dataclasses mirroring models
2a.8 Create `backend/pytest.ini` with `asyncio_mode = auto`
2a.9 Write unit tests for model column types and constraint definitions
2a.10 Verify `uv run pytest` passes with in-memory SQLite

**Depends on**: 1
**Acceptance criteria**:
- Models import without errors; UUID columns use SQLAlchemy 2.0 `Uuid` type
- `get_session` yields an `AsyncSession` per request
- `pytest` discovers and passes model unit tests
- `uv run ruff check .` passes

**Estimated changed lines**: ~190

**Note**: `test_message_model.py` was extracted to a follow-up slice 2a.2 (commit right after 2a) to fit the 400-line budget. Models and tests land in adjacent PRs; together they are the original slice 2.

---

## Slice 2b: DB Layer — Alembic Init + First Migration

**Goal**: Alembic configured for async, initial migration creating all three tables with indexes, FKs, and unique constraints.

**Files**:
- `backend/alembic.ini` (~20 lines)
- `backend/alembic/__init__.py` (3 lines)
- `backend/alembic/env.py` (~40 lines) — async engine, `run_sync` migration context
- `backend/alembic/versions/0001_init.py` (~80 lines) — creates users, conversations, messages tables

**Tasks**:
- [x] 2b.1 Create `backend/alembic.ini` pointing to `app.infrastructure.db.engine` and `app.db.models`
- [x] 2b.2 Create `backend/alembic/__init__.py` (intentionally omitted — conflicts with real alembic package import)
- [x] 2b.3 Patch `backend/alembic/env.py` for async — read `DATABASE_URL`, `connection.run_sync(do_migrations)`
- [x] 2b.4 Create `backend/alembic/versions/0001_init.py` — creates `users` (unique index on entraid_oid), `conversations` (FK user_id ON DELETE CASCADE, index on foundry_conversation_id), `messages` (FK conversation_id ON DELETE CASCADE)
- [x] 2b.5 Run `uv run alembic upgrade head` against dev SQLite; verify all 3 tables created
- [x] 2b.6 Run `uv run alembic upgrade head` again; verify idempotent (no destructive change)
- [x] 2b.7 Verify `uv run alembic downgrade -1` works and re-run upgrade cleanly

**Depends on**: 2a
**Acceptance criteria**:
- `alembic upgrade head` creates all 3 tables with correct schema
- `alembic history` shows exactly one migration
- Re-running upgrade is idempotent
- FK cascade delete verified manually (or via integration test in slice 7)

**Estimated changed lines**: ~190

---

## Slice 3: Entra ID JWT Validation

**Goal**: JWKS fetch + cache, PyJWT decode, `get_current_user` FastAPI dependency, and OID→users upsert.

**Files**:
- `backend/app/infrastructure/auth/__init__.py` (3 lines)
- `backend/app/infrastructure/auth/jwks.py` (~80 lines) — JWKSFetcher with 10-min TTL dict cache, exponential backoff retry
- `backend/app/infrastructure/auth/token.py` (~30 lines) — PyJWT decode with iss/aud/exp/sig checks
- `backend/app/infrastructure/auth/service.py` (~40 lines) — upsert user by OID
- `backend/app/infrastructure/auth/deps.py` (~30 lines) — `get_current_user` FastAPI dep

**Tasks**:
- [x] 3.1 Create `backend/app/api/auth/__init__.py`
- [x] 3.2 Create `backend/app/api/auth/jwks_fetcher.py` — `JwksFetcher` class: TTL cache (default 600s), `get_keys()` fetches JWKS, `aclose()` closes internal HTTP client, `reset()` clears cache
- [x] 3.3 Create `backend/app/services/user_service.py` — `UserService` with `get_or_create_by_oid(oid, email)` upsert
- [x] 3.4 Create `backend/app/api/auth/deps.py` — `get_current_user` FastAPI dep: extracts Bearer token, decodes JWT header for `kid`, looks up JWK, verifies RS256/aud/iss/exp via PyJWT, upserts user by OID
- [x] 3.5 Wire `JwksFetcher` in `backend/app/main.py` lifespan: created at startup, attached to `app.state`, closed at shutdown
- [x] 3.6 Write unit tests: `test_jwks_fetcher.py` (cache hit/miss/TTL/reset), `test_user_service.py` (upsert/create), `test_deps.py` (valid token + 7 error cases)
- [x] 3.7 Verify `uv run pytest tests/` passes (74 total: 56 pre-existing + 18 new), `uv run ruff check .` and `uv run ruff format --check .` pass

**Depends on**: 2b
**Acceptance criteria**:
- Valid token → user object returned by `get_current_user`
- Expired/bad-sig token → `401` with `detail = "token expired"` / `"invalid token"`
- Unknown `kid` → `401 "unknown kid"`
- New OID → `users` row inserted; returning OID → row returned without insert
- `uv run ruff check .` and `uv run ruff format --check .` pass

**Estimated changed lines**: ~871 across 13 files (split into 6 + 6.2 due to budget)

**Note**: Implementation diverges from design.md in file layout (`app/api/auth/` vs `app/infrastructure/auth/`) and scope (no exponential-backoff retry in this slice; JwksFetcher uses simple TTL without backoff). `token.py` logic was inlined into `deps.py`. The WebSocket `Sec-WebSocket-Protocol` auth is slice 7 — this slice covers HTTP `Authorization: Bearer` only.

---

## Slice 4: Conversation + Message Repository

**Goal**: Repository implementations for users, conversations, and messages; domain errors; application ports.

**Files**:
- `backend/app/repositories/__init__.py` (3 lines)
- `backend/app/repositories/users.py` (~30 lines) — `upsert_by_oid`
- `backend/app/repositories/conversations.py` (~50 lines) — `create`, `get_for_user`, `set_foundry_id`
- `backend/app/repositories/messages.py` (~30 lines) — `append`, `list`
- `backend/app/application/__init__.py` (3 lines)
- `backend/app/application/ports.py` (~40 lines) — `Protocol[UserRepo]`, `Protocol[ConversationRepo]`, `Protocol[MessageRepo]`
- `backend/app/domain/errors.py` (~25 lines) — `DomainError`, `NotFoundError`, `ConversationNotFoundError`

**Tasks**:
4.1 Create `backend/app/repositories/__init__.py`
4.2 Create `backend/app/repositories/users.py` — `upsert_by_oid(session, oid, email, display_name) → User`
4.3 Create `backend/app/repositories/conversations.py` — `create(session, user_id) → Conversation`, `get_for_user(session, user_id, conv_id) → Conversation | None`, `set_foundry_id(session, conv_id, foundry_id)`
4.4 Create `backend/app/repositories/messages.py` — `append(session, conv_id, role, content) → Message`, `list(session, conv_id) → list[Message]`
4.5 Create `backend/app/application/__init__.py`
4.6 Create `backend/app/application/ports.py` — `Protocol[UserRepo]`, `Protocol[ConversationRepo]`, `Protocol[MessageRepo]`
4.7 Create `backend/app/domain/errors.py` — `DomainError`, `NotFoundError`, `ConversationNotFoundError`
4.8 Write unit tests: create conversation, get_for_user returns None for wrong user, set_foundry_id, append user message, append assistant message, list returns chronological order, cross-user access blocked
4.9 Verify `uv run pytest tests/test_repositories.py` passes

**Depends on**: 3
**Acceptance criteria**:
- `create` inserts and returns a `Conversation` with UUID v4 PK
- `get_for_user` returns `None` when conversation belongs to another user
- `append` persists exactly one `Message` row
- `list` returns messages in `created_at` ascending order
- `uv run ruff check .` passes

**Estimated changed lines**: ~120

**Note**: `test_chat_turn.py` was extracted to a follow-up slice 4.2 (commit right after 4) to fit the 600-line budget. Streaming service and chat turn tests land in adjacent PRs; together they are the original slice 4.

---

## Slice 5: ConversationService + ChatTurnService Wiring (Batch 5)

**Goal**: Add a `ConversationService` that owns the lifecycle of `Conversation` rows and wire it into `ChatTurnService` so the orchestrator operates on a real `Conversation` row (not a placeholder created inline).

**Files**:
- `backend/app/services/conversation_service.py` (~230 lines) — `ConversationService` class: `get_or_create`, `link_foundry_session` (idempotent), `list_for_user`, `set_title`; plus `ConversationNotFoundError`.
- `backend/tests/services/test_conversation_service.py` (~206 lines) — 12 unit tests.
- `backend/app/services/chat_turn.py` (updated) — `execute()` now takes `conversation: Conversation` instead of `Conversation | None`; auto-links Foundry session after `StreamFinal`.
- `backend/app/services/__init__.py` (updated) — re-exports `ConversationService`, `ConversationNotFoundError`.
- `backend/tests/services/test_chat_turn.py` (updated) — updated 7 existing tests to pass explicit `Conversation`; added `test_links_foundry_session_after_stream_final`, `test_does_not_relink_when_session_id_unchanged`.

**Tasks**:
- [x] 5.1 Create `backend/app/services/conversation_service.py` — `ConversationService` with `get_or_create` (scoped to user), `link_foundry_session` (idempotent), `list_for_user` (ordered by `created_at desc`), `set_title` (255-char truncate); `ConversationNotFoundError`.
- [x] 5.2 Update `backend/app/services/chat_turn.py` — `execute()` signature changed: `conversation: Conversation` (required, not optional); `_link_foundry_session` called automatically after `StreamFinal` yields `service_session_id`.
- [x] 5.3 Update `backend/app/services/__init__.py` — re-export `ConversationService`, `ConversationNotFoundError`.
- [x] 5.4 Create `backend/tests/services/test_conversation_service.py` — 12 unit tests.
- [x] 5.5 Update `backend/tests/services/test_chat_turn.py` — adjust existing 7 tests; add 2 new tests.
- [x] 5.6 Verify `uv run pytest tests/` → 56/56 passed (43 existing + 13 new).
- [x] 5.7 Verify `uv run ruff check .` passes.
- [x] 5.8 Verify `uv run ruff format --check .` passes.

**Depends on**: 4, 4.2
**Acceptance criteria**:
- `ConversationService.get_or_create(user, conversation_id=None)` creates a new `Conversation` row and returns `(conv, True)`.
- `ConversationService.get_or_create(user, conversation_id=<uuid>)` returns the existing row scoped to that user, or raises `ConversationNotFoundError`.
- `ConversationService.link_foundry_session` is idempotent: linking the same `foundry_conversation_id` twice does not issue a second UPDATE.
- `ChatTurnService.execute(conversation=conv, ...)` no longer creates its own `Conversation` — the caller provides one.
- After `StreamFinal` yields a `service_session_id`, `ChatTurnService` sets `conversation.foundry_conversation_id` (only if currently `None`).
- All 56 tests pass.
- `uv run ruff check .` and `uv run ruff format --check .` both pass.

**Estimated changed lines**: ~728 (5 files)

---

## Slice 5: REST Endpoints (Non-Streaming)

**Goal**: `POST /conversations` and `GET /conversations/{id}/messages` with JWT auth and proper error envelopes.

**Files**:
- `backend/app/api/conversations.py` (~40 lines) — `POST /conversations` → 201 `{"id": "uuid"}`
- `backend/app/api/messages.py` (~40 lines) — `GET /conversations/{id}/messages` → 200 `{"messages": [...]}`
- `backend/app/api/deps.py` (~20 lines) — session + user deps (combines `get_session` + `get_current_user`)
- `backend/app/api/errors.py` (~30 lines) — `DomainError → JSON envelope`, `NotFoundError → 404`

**Tasks**:
5.1 Create `backend/app/api/deps.py` — combines `get_session` and `get_current_user` into one dependency
5.2 Create `backend/app/api/errors.py` — `exc_to_json(DomainError) → JSON`, `NotFoundError → 404 {"code","message"}`
5.3 Create `backend/app/api/conversations.py` — `POST /conversations` with `get_current_user` dep → 201 `{"id": "uuid"}`
5.4 Create `backend/app/api/messages.py` — `GET /conversations/{id}/messages` → 200 `{"messages": [{"id","role","content","created_at"}]}`, 404 on missing or cross-user
5.5 Write integration tests: create conversation returns 201, get messages returns 200 with array, cross-user get → 404, missing token → 401
5.6 Verify `uv run pytest tests/test_api.py` passes
5.7 Verify `uv run ruff check .` passes

**Depends on**: 4
**Acceptance criteria**:
- `POST /conversations` with valid JWT → 201 with conversation UUID
- `GET /conversations/{id}/messages` → 200 with message array in chronological order
- Cross-user access → 404 (not 403)
- Missing/invalid JWT → 401
- `uv run ruff check .` and `uv run ruff format --check .` pass

**Estimated changed lines**: ~110

---

## Slice 6: WebSocket Endpoint + Foundry Streaming Bridge

**Goal**: `/ws/chat` with JWT via `Sec-WebSocket-Protocol`, Foundry streaming bridge, per-turn persistence, and error mapping.

**Files**:
- `backend/app/infrastructure/foundry/__init__.py` (3 lines)
- `backend/app/infrastructure/foundry/client.py` (~60 lines) — `AIProjectClient` + `FoundryAgent` built once in lifespan
- `backend/app/infrastructure/foundry/stream.py` (~50 lines) — `FoundryStreamService.run_and_collect` wrapping `agent.run(stream=True, session=session)`
- `backend/app/services/__init__.py` (3 lines)
- `backend/app/services/foundry_stream.py` (re-export or thin wrapper — ~10 lines)
- `backend/app/services/chat_turn.py` (~80 lines) — `ChatTurnService`: validate ownership → persist user msg → resolve/create Foundry session → iterate stream → emit deltas → persist assistant msg once
- `backend/app/api/ws/__init__.py` (3 lines)
- `backend/app/api/ws/chat.py` (~90 lines) — `/ws/chat` handler: subprotocol extraction, handshake, state machine (ready→running→done), frame parsing, frame emission
- `backend/app/api/ws/errors.py` (~30 lines) — `WSError` enum: `foundry_transient`, `foundry_auth`, `foundry_payload`, `agent_not_found` → close codes
- `backend/app/main.py` (update lifespan) — open/close `AIProjectClient` on startup/shutdown
- `backend/app/logging.py` (~20 lines) — structlog JSON logger skeleton

**Tasks**:
6.1 Create `backend/app/infrastructure/foundry/__init__.py`
6.2 Create `backend/app/infrastructure/foundry/client.py` — `FoundryClient` class: `AzureCliCredential`, `AIProjectClient`, `FoundryAgent` built from env vars, `close()` method
6.3 Create `backend/app/infrastructure/foundry/stream.py` — `FoundryStreamService`: `run_and_collect(text, foundry_conversation_id)` → `(full_text, service_session_id)`, iterates `ResponseStream`, calls `get_final_response()` on completion
6.4 Create `backend/app/services/__init__.py`
6.5 Create `backend/app/services/foundry_stream.py` — thin re-export of `FoundryStreamService`
6.6 Create `backend/app/services/chat_turn.py` — `ChatTurnService`: ownership check → `messages.append(role="user")` → resolve/create Foundry session → `foundry_stream.run_and_collect()` → emit deltas → `messages.append(role="assistant")` on completion
6.7 Create `backend/app/api/ws/__init__.py`
6.8 Create `backend/app/api/ws/errors.py` — `WSError` enum mapping to close codes per foundry-bridge spec
6.9 Create `backend/app/api/ws/chat.py` — WebSocket handler: extract `bearer.<jwt>` from subprotocol, validate, echo subprotocol, parse inbound `user_message` envelope, call `ChatTurnService`, emit `assistant_delta` / `assistant_done` / `error` / `close` frames
6.10 Update `backend/app/main.py` — add lifespan context: open `FoundryClient` on startup, close on shutdown
6.11 Create `backend/app/logging.py` — structlog configure for JSON output, correlation_id context var
6.12 Write unit tests for `WSError` enum mapping, stream service with fake `ResponseStream`, `ChatTurnService` with mock repo + mock stream
6.13 Write integration tests: WS handshake with valid subprotocol echoes it, missing subprotocol → 1008, invalid token → 1008, chat turn with fake stream emits deltas then done
6.14 Verify `uv run pytest tests/test_ws.py` passes

**Depends on**: 5
**Acceptance criteria**:
- WS handshake with `Sec-WebSocket-Protocol: bearer.<jwt>` echoes the same subprotocol
- WS handshake without valid subprotocol → close 1008
- Valid message → user message persisted before Foundry call
- Stream deltas → one `assistant_delta` per non-empty `update.text`
- Stream done → exactly one `assistant` row persisted, `assistant_done` frame emitted
- Client disconnect mid-stream → no orphan assistant row
- Transient Foundry error → `error.code = "foundry_transient"`, connection kept open
- Auth/400/404 Foundry error → close 1011
- `uv run ruff check .` passes

**Estimated changed lines**: ~260

---

## Slice 7: Backend Tests (pytest + pytest-asyncio)

**Goal**: Comprehensive test scaffolding, fixtures, and tests covering auth, repositories, REST, and WebSocket.

**Files**:
- `backend/tests/__init__.py` (3 lines)
- `backend/tests/conftest.py` (~100 lines) — in-memory SQLite engine fixture, `AsyncSession` fixture, mock `AIProjectClient`, fake JWKS issuer with RS256 key pair, mock `ResponseStream`
- `backend/tests/test_repositories.py` (~80 lines) — full repository test suite
- `backend/tests/test_auth.py` (~60 lines) — JWKS cache TTL/refresh, token decode, upsert
- `backend/tests/test_api.py` (~60 lines) — REST endpoint tests
- `backend/tests/test_ws.py` (~80 lines) — WS handshake, chat turn, disconnect handling

**Tasks**:
- [x] 7.1 Create `backend/app/api/websockets/__init__.py`
- [x] 7.2 Create `backend/app/api/websockets/chat.py` — `/ws/chat/{conversation_id}` handler: subprotocol auth (`bearer.jwt.<token>`), JWT validation via `authenticate_ws()`, `ws_settings()` helper, streaming bridge, `ChatTurnService` execution, per-turn message persistence
- [x] 7.3 Wire `FoundryClient` and `ConversationService` in `backend/app/main.py` lifespan
- [x] 7.4 Re-export `chat_ws_router` in `backend/app/api/__init__.py`
- [x] 7.5 Run `uv run pytest --tb=short` and fix any failures
- [x] 7.6 Verify `uv run pytest` exit code 0 with all tests passing

**Depends on**: 5, 5.2 (ConversationService), 6 (Foundry streaming)
**Acceptance criteria**:
- WS handshake with `Sec-WebSocket-Protocol: bearer.jwt.<token>` echoes the same subprotocol
- WS handshake without valid subprotocol → close 1008
- Valid message → user message persisted before Foundry call
- Stream deltas → one `delta` frame per non-empty chunk
- Stream done → exactly one assistant row persisted, `done` frame emitted
- Client disconnect mid-stream → no orphan assistant row
- `uv run ruff check .` passes

**Estimated changed lines**: ~301 (3 files)

**Note**: `test_chat_endpoint.py` was committed as slice 7.2 (right after 7) to fit the 600-line budget. Production code and tests land in adjacent commits; together they are the original slice 7.

---

## Slice 8: Backend Observability + Error Mapping

**Goal**: Structured JSON logging with correlation IDs, Spanish user-facing error messages for all public endpoints, and WS close code enforcement.

**Files**:
- `backend/app/logging.py` (extend from skeleton) — structlog JSON, correlation_id var, request-level context
- `backend/app/api/ws/errors.py` (extend) — Spanish `message` per error code
- `backend/app/api/errors.py` (extend) — Spanish `message` per error code

**Tasks**:
8.1 Extend `backend/app/logging.py` — add `correlation_id` context variable, JSON renderer, `get_logger()` factory, log level from env
8.2 Extend `backend/app/api/ws/errors.py` — add Spanish `message` field to each `WSError` variant (`foundry_transient` → "Reintentá en unos segundos.", `foundry_auth` → "Error de autenticación con el agente.", etc.)
8.3 Extend `backend/app/api/errors.py` — add Spanish `message` to each `DomainError` JSON envelope
8.4 Add correlation_id to WS connection context and log every inbound frame at DEBUG, every outbound frame at INFO, every error at WARN with exception details
8.5 Write unit tests: Spanish message map covers all error codes, correlation_id present in log output
8.6 Verify `uv run pytest tests/test_errors.py` (or add to existing test files) passes
8.7 Verify `uv run ruff check .` passes

**Depends on**: 6, 7
**Acceptance criteria**:
- Every `error` WS frame includes a Spanish `message` and stable English `code`
- Every `close` WS frame includes the correct numeric code (1008 for auth, 1011 for server error)
- All log output is structured JSON with `correlation_id` field
- `uv run ruff check .` passes

**Estimated changed lines**: ~140

**Note**: `test_conversations.py` was extracted to a follow-up slice 8.2 (commit right after 8) to fit the 600-line budget. REST endpoints and tests land in adjacent PRs; together they are the original slice 8.

---

## Slice 9: Frontend Bootstrap (Vite + React 19 + TS + Tailwind v4 + MSAL + Zustand)

**Goal**: Scaffold the `frontend/` project with Vite, React 19, TypeScript, Tailwind v4, MSAL React provider, login page, and Zustand store skeletons. Runs in parallel with slices 1–6.

**Files**:
- `frontend/package.json` (~40 lines) — vite, react, react-dom, typescript, tailwindcss, @azure/msal-browser, @azure/msal-react, zustand, @testing-library/react, vitest
- `frontend/tsconfig.json` (~20 lines)
- `frontend/vite.config.ts` (~15 lines)
- `frontend/index.html` (~15 lines)
- `frontend/postcss.config.js` (~5 lines)
- `frontend/.env.example` (~10 lines) — VITE_API_BASE, VITE_ENTRA_CLIENT_ID, VITE_ENTRA_TENANT_ID
- `frontend/vitest.config.ts` (~15 lines)
- `frontend/src/main.tsx` (~10 lines)
- `frontend/src/index.css` (~5 lines) — tailwind v4 entry
- `frontend/src/app/App.tsx` (~20 lines) — MsalProvider + Router
- `frontend/src/app/router.tsx` (~20 lines) — routes: "/" → Login, "/chat" → Chat
- `frontend/src/app/msal.ts` (~30 lines) — PublicClientApplication config
- `frontend/src/store/auth.ts` (~30 lines) — Zustand auth store: account, accessToken, getToken()
- `frontend/src/store/chat.ts` (~20 lines) — skeleton: threadId, messages[], isStreaming, error
- `frontend/src/components/ui/Button.tsx` (~15 lines)
- `frontend/src/components/ui/Spinner.tsx` (~10 lines)
- `frontend/src/pages/Login.tsx` (~40 lines) — "Iniciar sesión con Microsoft" button, MSAL loginPopup, error display
- `frontend/src/lib/errors.ts` (~20 lines) — code → neutral-professional-Spanish message map

**Tasks**:
9.1 Create `frontend/package.json` with all dependencies
9.2 Create `frontend/tsconfig.json` with strict mode
9.3 Create `frontend/vite.config.ts` with React plugin
9.4 Create `frontend/index.html`
9.5 Create `frontend/postcss.config.js` with tailwindcss plugin
9.6 Create `frontend/.env.example`
9.7 Create `frontend/vitest.config.ts` with jsdom
9.8 Create `frontend/src/main.tsx` — render App
9.9 Create `frontend/src/index.css` — `@import "tailwindcss"`
9.10 Create `frontend/src/app/App.tsx` — MsalProvider wrapping Router
9.11 Create `frontend/src/app/router.tsx` — Routes: "/" → Login, "/chat" → Chat
9.12 Create `frontend/src/app/msal.ts` — PublicClientApplication config from env vars
9.13 Create `frontend/src/store/auth.ts` — Zustand store: account, accessToken, getToken() wrapping MSAL acquireTokenSilent
9.14 Create `frontend/src/store/chat.ts` — skeleton: threadId, messages[], isStreaming, error, appendDelta, clearError
9.15 Create `frontend/src/components/ui/Button.tsx`
9.16 Create `frontend/src/components/ui/Spinner.tsx`
9.17 Create `frontend/src/pages/Login.tsx` — MSAL loginPopup flow, error handling, redirect to /chat on success
9.18 Create `frontend/src/lib/errors.ts` — code → Spanish message map
9.19 Run `npm install && npm run dev` and verify `http://localhost:5173` shows login page
9.20 Run `npm test` and verify vitest discovers all tests

**Depends on**: —
**Acceptance criteria**:
- `npm run dev` serves on `http://localhost:5173`
- Login page renders with "Iniciar sesión con Microsoft" button
- After MSAL login success, user lands on `/chat`
- `npm test` exit code 0
- `npm run build` succeeds without type errors

**Estimated changed lines**: ~280

---

## Slice 10: Chat Page + WebSocket Client + Persistence Hooks

**Goal**: Full chat UI with native WebSocket client, thread_id in localStorage, resume on mount, "Nueva conversación", and component tests.

**Files**:
- `frontend/src/pages/Chat.tsx` (~100 lines) — Chat page: TopBar, ChatList, Composer; resume or mint thread on mount
- `frontend/src/store/ws.ts` (~50 lines) — Zustand WS store: connect(token), disconnect(), sendUserMessage(content), reconnect on 1006, no-reconnect on 1008
- `frontend/src/store/chat.ts` (extend) — add `appendDelta(text)`, `setDone(message_id, content)`, `newConversation()`
- `frontend/src/lib/api.ts` (~30 lines) — fetch wrapper with `Authorization: Bearer <jwt>`
- `frontend/src/lib/ws.ts` (~50 lines) — native WebSocket factory: `createWsClient(url, token)` → `WebSocket` with subprotocol, backoff helpers
- `frontend/src/lib/thread.ts` (~30 lines) — localStorage key `csa:thread_id:v1`: `getThreadId()`, `setThreadId(id)`, `clearThreadId()`
- `frontend/src/components/MessageBubble.tsx` (~40 lines) — user (right) / assistant (left) bubble
- `frontend/src/components/Composer.tsx` (~40 lines) — textarea + send button, submit on Enter/Ctrl+Enter
- `frontend/src/components/ChatList.tsx` (~30 lines) — scrollable message list
- `frontend/src/components/TopBar.tsx` (~30 lines) — user identity, "Nueva conversación" button
- `frontend/tests/ws.test.ts` (~60 lines) — connect with subprotocol, token never in URL, reconnect on 1006, no-reconnect on 1008
- `frontend/tests/chat.test.ts` (~50 lines) — appendDelta immutability, setDone, newConversation clears messages
- `frontend/tests/thread.test.ts` (~30 lines) — getThreadId resume, setThreadId, clearThreadId, 404 → mint new

**Tasks**:
10.1 Extend `frontend/src/store/chat.ts` — add `appendDelta(text)` (immutable), `setDone(message_id, content)`, `newConversation()` (clear messages + threadId)
10.2 Create `frontend/src/lib/api.ts` — fetch wrapper: `GET(url)` and `POST(url, body)` with `Authorization: Bearer <jwt>` header
10.3 Create `frontend/src/lib/thread.ts` — `getThreadId()` → localStorage `csa:thread_id:v1` or null, `setThreadId(id)`, `clearThreadId()`
10.4 Create `frontend/src/lib/ws.ts` — `createWsClient(apiBase, token)` → `new WebSocket(url, 'bearer.' + token)`, backoff constants
10.5 Create `frontend/src/store/ws.ts` — Zustand store: `connect(token)`, `disconnect()`, `sendUserMessage(content)`, dispatching `assistant_delta` / `assistant_done` / `error` / `close` to chat store; reconnect on 1006 with `min(2^attempt, 30)s` backoff, max 5 attempts; no-reconnect on 1008
10.6 Create `frontend/src/components/MessageBubble.tsx` — renders role + content, timestamp; user = right-aligned, assistant = left-aligned
10.7 Create `frontend/src/components/Composer.tsx` — textarea (max 4000 chars), send button; `onSubmit` calls `wsStore.sendUserMessage()`
10.8 Create `frontend/src/components/ChatList.tsx` — maps `chatStore.messages` to `MessageBubble`s, auto-scrolls to bottom
10.9 Create `frontend/src/components/TopBar.tsx` — displays `authStore.account`, "Nueva conversación" button calls `chatStore.newConversation()` + `threadStore.clearThreadId()`
10.10 Create `frontend/src/pages/Chat.tsx` — on mount: if `threadId` exists, call `GET /conversations/{id}/messages` and hydrate; if 404, clear and `POST /conversations`; render TopBar + ChatList + Composer; show empty-state assistant message "Hola, soy el agente de soporte. ¿En qué te puedo ayudar?"
10.11 Create `frontend/tests/ws.test.ts` — MockWebSocket; test connect adds subprotocol, token not in URL, reconnect on 1006, no-reconnect on 1008
10.12 Create `frontend/tests/chat.test.ts` — test appendDelta produces new reference, setDone replaces last message, newConversation clears
10.13 Create `frontend/tests/thread.test.ts` — test getThreadId resume, setThreadId, clearThreadId, 404 triggers mint
10.14 Run `npm test` and fix failures
10.15 Verify `npm run build` succeeds

**Depends on**: 9, 6
**Acceptance criteria**:
- Chat page loads and shows empty-state message on first visit
- Sending a message streams tokens in real time (delta frames)
- Refresh preserves the same conversation (thread_id in localStorage + server hydration)
- "Nueva conversación" clears the visible history and creates a fresh server-side thread
- `npm test` passes
- `npm run build` succeeds without type errors

**Estimated changed lines**: ~320

---

## Commit Plan

Each slice maps to one conventional commit (or chained PR). Tests and docs are included with the slice that introduces the behavior they verify.

| Slice | Commit subject | Commit body focus | Files committed |
|-------|---------------|-------------------|-----------------|
| 1 | `feat(backend): bootstrap uv + FastAPI app with healthz` | Quickstart, env mirroring, pydantic-settings config | pyproject.toml, uv.lock, .env, .env.example, app/main.py, app/config.py, app/api/health.py, README.md |
| 2a | `feat(backend): add async SQLAlchemy engine, session dep, and domain models` | UUID v4 PKs, typed declarative models, WAL PRAGMA | app/infrastructure/db/engine.py, session.py, models.py, app/domain/entities.py, pytest.ini |
| 2b | `feat(backend): add Alembic init and 0001_init migration` | Async env, FK cascade, unique index on entraid_oid | alembic.ini, alembic/env.py, alembic/versions/0001_init.py |
| 3 | `feat(backend): add Entra ID JWT validation with JWKS cache` | RS256 validation, 10-min TTL cache, exponential backoff, user upsert | app/infrastructure/auth/jwks.py, token.py, service.py, deps.py |
| 4 | `feat(backend): add repositories for users, conversations, messages` | Protocol contracts, ownership check, append/list | app/repositories/*.py, app/application/ports.py, app/domain/errors.py |
| 5 | `feat(backend): add REST endpoints for conversation lifecycle` | POST /conversations, GET /conversations/{id}/messages, 404 cross-user | app/api/conversations.py, messages.py, deps.py, errors.py |
| 6 | `feat(backend): add WebSocket /ws/chat with Foundry streaming bridge` | Subprotocol auth, delta streaming, per-turn persistence, error mapping | app/infrastructure/foundry/client.py, stream.py, app/services/chat_turn.py, app/api/ws/chat.py, errors.py, main.py (lifespan), logging.py |
| 7 | `feat(backend): add pytest + pytest-asyncio test suite` | In-memory SQLite, mock Foundry, fake JWKS, full coverage | tests/conftest.py, test_repositories.py, test_auth.py, test_api.py, test_ws.py |
| 8 | `feat(backend): add structlog JSON observability and Spanish error messages` | Correlation ID, Spanish user-facing messages per error code | app/logging.py, app/api/ws/errors.py, app/api/errors.py |
| 9 | `feat(frontend): scaffold Vite + React 19 + MSAL + Zustand` | Vite config, MSAL provider, login page, auth/chat store skeletons | package.json, vite.config.ts, tsconfig.json, src/main.tsx, src/app/App.tsx, router.tsx, msal.ts, store/auth.ts, store/chat.ts, pages/Login.tsx, lib/errors.ts, components/ui/*.tsx |
| 10 | `feat(frontend): add chat page with WebSocket client and thread persistence` | WS store with reconnect, localStorage thread_id, chat UI components, tests | src/pages/Chat.tsx, src/store/ws.ts, src/lib/api.ts, ws.ts, thread.ts, components/*.tsx, tests/*.ts |
