# Design: MVP Customer-Support Chat

## 1. Architecture Overview

The system is a single-tenant web product. The backend follows a hexagonal / clean-architecture layout: `domain` (entities + errors), `application/ports` (Protocols), `infrastructure` (DB, auth, Foundry adapters), `services` (use-cases / orchestrators), `api` (REST + WS adapters), `repositories` (data access). The frontend is a Vite + React 19 SPA, layered as `app/`, `store/`, `lib/`, `components/`, `pages/`.

Two ingress paths converge on the FastAPI app:

```
  [Vite/React 19 FE]                            [FastAPI BE]                              [Foundry]
        |                                              |                                       |
        |--- POST /conversations ------------------->  |---[repositories/users.py]------>      |
        |--- GET  /conversations/:id/messages ------>   |---[repositories/conversations.py]->  |
        |--- Authorization: Bearer <jwt>              |---[repositories/messages.py]----> [SQLite]
        |                                              |                                       |
        |--- WS /ws/chat (subprotocol bearer.<jwt>) >  |---[api/ws/chat.py]                       |
        |                                              |    |                                    |
        |                                              |    +-->[services/chat_turn.py]           |
        |                                              |          |                              |
        |                                              |          +--persist user msg              |
        |                                              |          +-->[services/foundry_stream.py]  |
        |                                              |                |                         |
        |                                              |                | AIProjectClient         |
        |                                              |                v                         |
        |                                              |          FoundryAgent.run(text,         |
        |                                              |             stream=True, session=…)  --->|
        |<-- assistant_delta JSON ------------------- |<---------+ (async for update in stream) |
        |<-- assistant_done  JSON ------------------- |<--persist ONE assistant row             |
```

The chat use-case (`services/chat_turn.py`) is the only place that knows about both persistence and the bridge. The WS handler (`api/ws/chat.py`) is a thin adapter that parses frames, calls the use-case, and serializes frames back. Foundry configuration is read once at startup from `example/.env` keys; nothing in the runtime redefines the system prompt or model.

## 2. Backend Module Layout (`backend/`)

```
backend/
├── pyproject.toml                # uv-managed, [tool.ruff], [tool.pytest.ini_options]
├── uv.lock
├── .env                          # mirrors example/.env keys
├── .env.example
├── pytest.ini                    # asyncio_mode = auto
├── alembic.ini
├── alembic/
│   ├── env.py                    # async engine, run_sync
│   └── versions/0001_init.py
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI(), lifespan opens/closes Foundry client
│   ├── config.py                 # pydantic-settings Settings
│   ├── logging.py                # structlog JSON
│   ├── domain/
│   │   ├── entities.py           # User, Conversation, Message dataclasses
│   │   └── errors.py             # DomainError taxonomy
│   ├── application/
│   │   └── ports.py              # Protocol[FoundryClient], Protocol[UserRepo] …
│   ├── api/
│   │   ├── __init__.py           # re-exports auth and ws routers
│   │   ├── auth/
│   │   │   ├── jwks_fetcher.py  # JwksFetcher + in-mem TTL cache
│   │   │   ├── deps.py          # get_current_user FastAPI dep
│   │   │   └── __init__.py
│   │   ├── websockets/
│   │   │   ├── chat.py          # /ws/chat/{conversation_id} handler
│   │   │   └── __init__.py
│   │   ├── conversations.py      # POST /conversations
│   │   ├── messages.py          # GET /conversations/{id}/messages
│   │   ├── deps.py              # session + user deps
│   │   ├── errors.py            # exception → JSON envelope
│   │   └── health.py            # GET /healthz
│   ├── domain/
│   │   ├── entities.py          # User, Conversation, Message dataclasses
│   │   └── errors.py           # DomainError taxonomy
│   ├── infrastructure/
│   │   └── db/
│   │       ├── engine.py        # async_engine + PRAGMA listener
│   │       ├── session.py       # async_sessionmaker + get_session dep
│   │       └── models.py        # SQLAlchemy 2.0 typed declarative
│   ├── repositories/
│   │   ├── users.py             # upsert_by_oid
│   │   ├── conversations.py     # create, get_for_user
│   │   └── messages.py          # append, list
│   ├── services/
│   │   ├── foundry/
│   │   │   ├── client.py       # FoundryClient: AIProjectClient + FoundryAgent
│   │   │   └── __init__.py
│   │   ├── foundry_stream.py    # FoundryStreamService.run_and_collect
│   │   ├── chat_turn.py        # ChatTurnService: persist→run→persist
│   │   ├── conversation_service.py  # ConversationService lifecycle
│   │   ├── user_service.py     # UserService.get_or_create_by_oid
│   │   └── stream_events.py    # StreamDelta, StreamError, StreamFinal
│   └── settings.py             # pydantic-settings Settings
└── tests/
    ├── api/
    │   ├── __init__.py
    │   ├── conftest.py          # RSA keypair, fake JWKS, create_test_token
    │   ├── test_jwks_fetcher.py
    │   ├── test_user_service.py
    │   ├── test_deps.py
    │   └── websockets/
    │       ├── __init__.py
    │       └── test_chat_endpoint.py  # 10 WS acceptance tests
    └── services/
        ├── test_conversation_service.py
        ├── test_foundry_stream.py
        └── test_chat_turn.py
```

**File budget**: every file ≤ 150 lines (clean-arch sizing). The orchestrator (`chat_turn.py`) is the only file allowed to know about both persistence and the bridge. The bridge (`foundry_stream.py`) is the only file that imports `agent_framework` and `azure.ai.projects`.

## 3. DB Design

SQLAlchemy 2.0 typed declarative, `Uuid` columns (Python-side `uuid.uuid4()` default), `DateTime` with `server_default=func.now()`. Engine URL is `DATABASE_URL` driven — `sqlite+aiosqlite:///./dev.db` in dev, swap to `postgresql+asyncpg://…` for prod (release 2) with zero model change.

```python
# app/infrastructure/db/models.py
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    entraid_oid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(256))
    display_name: Mapped[str | None] = mapped_column(String(256))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    foundry_conversation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    title: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)   # user|assistant|system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    foundry_message_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
```

Alembic: `alembic init` produces a sync `env.py`; we patch it to read the async `DATABASE_URL` and run migrations via `connection.run_sync(do_migrations)`. The first migration `0001_init.py` creates the three tables, the unique index on `users.entraid_oid`, the FKs with `ON DELETE CASCADE`, and the indexes on `conversations.user_id`, `conversations.foundry_conversation_id`, and `messages.conversation_id`. `PRAGMA foreign_keys = ON` is attached via a `event.listens_for(engine.sync_engine, "connect")` listener in `db/engine.py`.

Repository contracts (Protocol in `application/ports.py`):
- `users.upsert_by_oid(oid, email, display_name) -> User` — atomic insert-or-select keyed on `entraid_oid`.
- `conversations.create(user_id) -> Conversation` / `get_for_user(user_id, conv_id) -> Conversation | None` / `set_foundry_id(conv_id, foundry_id)`.
- `messages.append(conv_id, role, content) -> Message` / `list(conv_id) -> list[Message]`.

## 4. Auth Flow

```
  FE (MSAL React)                         BE (FastAPI)                        Entra ID
    |  loginPopup (popup)                    |                                    |
    |<-- accessToken (1h, aud=api) ---------|                                    |
    |                                        |                                    |
    |  GET /conversations                    |--- GET /.well-known/openid/.....>|
    |  Authorization: Bearer <jwt> --------> |<-- {keys:[{kid,n,e}]} -----------|
    |                                        |  (cache 10 min in proc mem)       |
    |                                        |  PyJWT.decode(jwt, key, alg=RS256,|
    |                                        |     audience=APP_AUDIENCE,         |
    |                                        |     issuer=https://sts.windows.net/<tid>/v2.0)
    |                                        |  → claims.oid → upsert users      |
    |<-- 201 {id: …} ----------------------- |                                    |
```

WS variant: instead of the `Authorization` header, the JWT rides inside the WebSocket subprotocol negotiation.

```
    FE                                              BE
    |--- Upgrade: ws://…/ws/chat ----------------->|
    |    Sec-WebSocket-Protocol: bearer.<jwt>      |
    |                                              |-- extract bearer.<jwt>
    |                                              |-- decode (same path as REST)
    |                                              |-- on success: respond with same subprotocol echoed
    |<-- 101 Switching Protocols ------------------|
    |    Sec-WebSocket-Protocol: bearer.<jwt>      |
    |--- frames {…} ----------------------------->|
```

Any other transport (URL `?token=…`, `Cookie`, custom header) is **rejected with close 1008** and the token is never logged. A pre-merge grep (`grep -RnE 'token=|\\?.*jwt' backend/app/ws`) enforces it.

**JWKS cache**: in-process `dict[str, JWK]` keyed by `kid`, TTL = 10 min. On `unknown kid` we force one refresh; on JWKS unreachable we retry with exponential backoff `1, 2, 4, 8, 16, 30s` cap. Surfaces as REST `503 service_unavailable` or WS `1011` with Spanish `message`.

## 5. WebSocket Lifecycle

**Inbound envelope** (one object per frame):

```json
{ "type": "user_message", "content": "Hola", "conversation_id": "0192…uuid4" }
```

**Outbound frames**:

```json
{ "type": "assistant_delta", "delta": "¿En qué " }
{ "type": "assistant_delta", "delta": "puedo ayudar?" }
{ "type": "assistant_done",  "message_id": "0192…", "content": "¿En qué puedo ayudar?" }
{ "type": "error", "code": "foundry_transient", "message": "Reintentá en unos segundos." }
{ "type": "close",  "code": 1011, "reason": "internal_error" }
```

**Lifecycle states**: `handshake → ready → running → done → ready` (or `→ closed`).

1. **Handshake** — extract subprotocol; if invalid → close 1008. If valid → echo back the same subprotocol, transition to `ready`.
2. **Receive** — parse JSON. Validate `type ∈ {"user_message"}`, `content` length 1..4000, `conversation_id` is a UUID or `null`. Validation failures emit an `error` frame; the connection stays open.
3. **Run** — `ChatTurnService.handle(session, user, conv_id, content)`:
   1. ownership check via `conversations.get_for_user(user.id, conv_id)` → 404 envelope if missing.
   2. persist `user` row, commit.
   3. resolve Foundry session: `create_session()` if first turn, `agent.get_session(service_session_id=…)` otherwise. Update `conversations.foundry_conversation_id` if newly minted.
   4. iterate `ResponseStream`; for each non-empty `update.text` emit one `assistant_delta`.
   5. on completion, call `await stream.get_final_response()` and persist **exactly one** `assistant` row with the full text and the returned `message_id`; emit `assistant_done`.
4. **Errors** — Foundry exceptions mapped per the foundry-bridge spec: `foundry_transient` keeps the connection open, `foundry_auth` / `foundry_payload` / `agent_not_found` close with 1011.
5. **Disconnect mid-stream** — FastAPI raises `WebSocketDisconnect` inside the iter loop; we cancel the Foundry task and **do not persist** a partial assistant row.

**Reconnect strategy** (server is source of truth): the FE handles `1006` with exponential backoff `min(2^attempt, 30)s`, max 5 attempts. On `1008` the FE does **not** auto-reconnect and redirects to `/`. After any reconnect, the FE rehydrates via `GET /conversations/{id}/messages`; it does **not** replay queued client-side sends.

## 6. Foundry Bridge Module

`infrastructure/foundry/client.py` owns a single `AIProjectClient` (async) and `AzureCliCredential` (async), opened in the FastAPI `lifespan` context and closed on shutdown. The `FoundryAgent` is built once from `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_AI_AGENT_NAME`, `AGENT_VERSION` — mirroring `example/001-support-agent.py`.

`services/foundry_stream.py` exposes the streaming primitive (the only file that imports `agent_framework`):

```python
class FoundryStreamService:
    def __init__(self, agent: FoundryAgent, on_delta: Callable[[str], Awaitable[None]]): ...

    async def run_and_collect(
        self, *, text: str, foundry_conversation_id: str | None,
    ) -> tuple[str, str | None]:
        session = (
            self._agent.get_session(service_session_id=foundry_conversation_id)
            if foundry_conversation_id
            else self._agent.create_session()
        )
        stream = self._agent.run(text, stream=True, session=session)
        try:
            async for update in stream:
                if update.text:
                    await self._on_delta(update.text)
        except WebSocketDisconnect:
            stream.close()                       # cancel Foundry task
            raise
        final = await stream.get_final_response()
        return final.text, session.service_session_id
```

**Error mapping** in `api/ws/errors.py`:
| Source | Stable code | Close |
|---|---|---|
| 5xx / 429 / timeout | `foundry_transient` | keep open |
| credential / token | `foundry_auth` | 1011 |
| 400-class | `foundry_payload` | 1011 |
| `get_version` miss | `agent_not_found` | 1011 |
| `service_session_id` no longer valid | log WARN, clear `foundry_conversation_id`, recreate (best-effort replay from `messages`) | keep open |

The original exception is logged via `structlog` with a per-connection `correlation_id` at WARN; the WS frame carries only the stable English `code` and a Spanish `message`.

## 7. Frontend Module Layout (`frontend/`)

```
frontend/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── index.html
├── postcss.config.js
├── .env.example                 # VITE_API_BASE, VITE_ENTRA_CLIENT_ID, VITE_ENTRA_TENANT_ID
├── vitest.config.ts
├── src/
│   ├── main.tsx
│   ├── index.css                # tailwind v4 entry
│   ├── app/
│   │   ├── App.tsx              # MsalProvider + Router
│   │   ├── router.tsx           # "/" → Login, "/chat" → Chat
│   │   └── msal.ts              # PublicClientApplication config
│   ├── store/
│   │   ├── auth.ts              # Zustand: account, accessToken, getToken()
│   │   ├── chat.ts              # Zustand: threadId, messages[], isStreaming, error
│   │   └── ws.ts                # Zustand: connect/dispatch/send
│   ├── lib/
│   │   ├── api.ts               # fetch wrapper; Authorization: Bearer <jwt>
│   │   ├── ws.ts                # native WebSocket + backoff
│   │   ├── thread.ts            # localStorage 'csa:thread_id:v1'
│   │   └── errors.ts            # code → neutral-Spanish message map
│   ├── components/
│   │   ├── ui/Button.tsx        # atom
│   │   ├── ui/Spinner.tsx       # atom
│   │   ├── MessageBubble.tsx    # molecule
│   │   ├── Composer.tsx         # molecule
│   │   ├── ChatList.tsx         # organism
│   │   └── TopBar.tsx           # organism
│   └── pages/
│       ├── Login.tsx
│       └── Chat.tsx
└── tests/
    ├── ws.test.ts
    ├── chat.test.ts
    └── thread.test.ts
```

**Zustand stores**:
- `auth` — `account`, `accessToken`, `getToken()` calls `msalInstance.acquireTokenSilent({ account, scopes: [API_SCOPES] })` with a 5-minute skew.
- `chat` — `threadId`, `messages: ChatMessage[]`, `isStreaming`, `error`. `appendDelta(text)` is **immutable**: clones the last message and appends; rest of the array is unchanged.
- `ws` — `connect(token)`, `disconnect()`, `sendUserMessage(content)`, dispatches for `assistant_delta` / `assistant_done` / `error` / `close`. Reconnect logic (exponential backoff, max 5) lives here.

**MSAL config** (`app/msal.ts`): `PublicClientApplication` with `auth.clientId`, `auth.authority = 'https://login.microsoftonline.com/<tenant>'`, `cache.cacheLocation = 'localStorage'`. Interactive login uses `loginPopup({ scopes: [API_SCOPES, 'openid', 'profile'] })`. Silent refresh uses `acquireTokenSilent`. UI strings are neutral professional Spanish (e.g., "Iniciar sesión con Microsoft", "No pudimos iniciar sesión. Probá de nuevo.", "Nueva conversación", "Hola, soy el agente de soporte. ¿En qué te puedo ayudar?").

## 8. Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit (BE) | Domain entities, error mappers, JWKS cache TTL/refresh, JWS parse, content-size guard. | `pytest` plain. |
| Unit (FE) | `chat` store immutability, `thread` localStorage resume/mint, `errors.ts` map. | `vitest` + jsdom. |
| Integration (BE) | Repository CRUD with FK cascade, auth dep (valid/expired/bad signature/aud mismatch), REST shapes (status, JSON, 404 cross-user), WS handshake (subprotocol echo, 1008 on missing/bad), chat_turn service with a fake `ResponseStream` (no network). | `pytest-asyncio`, `httpx.AsyncClient` against the FastAPI app, in-memory `sqlite+aiosqlite:///:memory:`, mock JWKS issuer signing a real RS key. |
| Component (FE) | `ws` client connect / reconnect on 1006 / no-reconnect on 1008 / token never in URL, `chat` mutations, thread reconciliation. | `vitest` + `@testing-library/react`, `WebSocket` polyfilled by a `MockWebSocket`. |
| E2E | Skipped in release 1 (no CI; manual smoke). | n/a |

`uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `npm test` MUST all pass before a slice lands. Coverage threshold is 0 (release 1 ships green-only). Release 2 will set up CI per the `delivery` spec.

## 9. Risks & Mitigations

| # | Risk | Likelihood | Impact | Owner | Mitigation |
|---|---|---|---|---|---|
| R1 | `FoundryAgent.run(stream=True)` signature drift in `agent_framework`. | Med | Slice 6 blocks. | BE lead | Pin `agent-framework>=1.8.0,<2.0.0`; bridge integration test consumes a fake `ResponseStream` so unit tests don't depend on the live SDK shape. |
| R2 | Foundry `service_session_id` becomes invalid mid-session (manual edit, restart, tenant migration). | Med | First turn after restart 500s. | BE lead | Catch `conversation_not_found` in `run_and_collect`; clear `foundry_conversation_id`; recreate; warn-log. |
| R3 | Entra JWKS endpoint unreachable at boot or under attack. | Med | 503 storm on every WS connect. | BE lead | 10-min TTL cache; exponential backoff (1→2→4→8→16→30s cap); circuit-break → 503 with Spanish `message`. |
| R4 | JWT leaked via WS URL query string (logs, referrers, history). | High | Token theft. | BE lead | Reject query-string token at handshake; pre-merge grep `grep -RnE 'token=|\\?.*jwt' backend/app/ws`. |
| R5 | localStorage `thread_id` desyncs with server (manual DB edit, restart, swap device). | Med | 404 loop on the FE. | FE lead | 404 handler in `lib/ws.ts` clears the key and calls `POST /conversations`. |
| R6 | `aiosqlite` used in prod by mistake. | Low | Prod crash under multi-writer. | BE lead | Engine URL driven by `DATABASE_URL`; smoke check in dev: `grep -Rn "aiosqlite" backend/app && [ "$ENV" = "prod" ] && exit 1`. |
| R7 | Slice 2 (DB + Alembic) blows the 400-line budget. | Med | Forces mid-flight split. | sdd-tasks | Forecast line count; pre-emptively split 2a (engine + models + session) and 2b (alembic + 0001_init). |
| R8 | `aiosqlite` + WS concurrency. | Low | "database is locked" under load. | BE lead | `check_same_thread=False`, `pool_size=1`, `PRAGMA journal_mode=WAL` per connection. |
| R9 | Rioplatense tone leaks into log/structured error fields. | Low | Tone inconsistency. | FE lead | UI strings live in `lib/errors.ts`; never interpolated into log fields. |
| R10 | `gpt-5-mini` system prompt drift between agent versions. | Low | Tone changes silently. | Foundry lead | Pin `AGENT_VERSION`; treat prompt as immutable (spec: foundry-bridge Requirement: Foundry model and prompt are source of truth). |

## 10. Slice-to-File Mapping (≤ 400 changed lines per slice)

`force-chained` delivery: one chained PR per slice. Counts are *created / first-modified*; over-budget triggers a split before merge.

| # | Slice | New / modified files (relative to `backend/` or `frontend/`) | Δ lines |
|---|---|---|---|
| 1 | BE bootstrap (uv + FastAPI) | `pyproject.toml`, `.env`, `.env.example`, `app/__init__.py`, `app/main.py`, `app/config.py`, `app/api/__init__.py`, `app/api/health.py`, `README.md` | ~90 |
| 2 | DB (engine + models + Alembic) | `app/infrastructure/__init__.py`, `app/infrastructure/db/__init__.py`, `app/infrastructure/db/engine.py`, `app/infrastructure/db/session.py`, `app/infrastructure/db/models.py`, `app/domain/__init__.py`, `app/domain/entities.py`, `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_init.py`, `pytest.ini`, `tests/db/test_message_model.py` (→ slice 2a.2) | ~380. **If forecast > 400, split into 2a (engine + models + session) and 2b (alembic + 0001_init) — both still capped at 400.** |
| 3 | Entra JWT validation | `app/infrastructure/auth/__init__.py`, `app/infrastructure/auth/jwks.py`, `app/infrastructure/auth/token.py`, `app/infrastructure/auth/service.py`, `app/infrastructure/auth/deps.py` | ~160 |
| 4 | Repositories | `app/repositories/__init__.py`, `app/repositories/users.py`, `app/repositories/conversations.py`, `app/repositories/messages.py`, `app/application/__init__.py`, `app/application/ports.py`, `app/domain/errors.py` | ~120 |
| 4-streaming | Foundry Streaming + Chat Turn Orchestrator | `app/services/stream_events.py`, `app/services/foundry_stream.py`, `app/services/chat_turn.py`, `tests/services/test_foundry_stream.py`; `tests/services/test_chat_turn.py` (→ slice 4.2) | ~567 |
| 5 | REST endpoints | `app/api/conversations.py`, `app/api/messages.py`, `app/api/deps.py`, `app/api/errors.py` | ~110 |
| 6 | WS + Foundry bridge | `app/services/foundry/__init__.py`, `app/services/foundry/client.py`, `app/services/foundry/stream.py`, `app/services/__init__.py`, `app/services/foundry_stream.py`, `app/services/chat_turn.py`, `app/api/websockets/__init__.py`, `app/api/websockets/chat.py`, `app/main.py` (lifespan) | ~260 |
| 7 | BE WS endpoint + acceptance tests | `backend/app/api/websockets/chat.py` (slice 7); `backend/tests/api/websockets/test_chat_endpoint.py` (slice 7.2) | ~301 + ~632 |
| 8 | BE observability + error mapping | `app/logging.py` (extend), `app/api/ws/errors.py` (extend), `app/api/errors.py` (extend); `backend/tests/api/rest/test_conversations.py` (→ slice 8.2) | ~140 |
| 9 | FE bootstrap | `package.json`, `tsconfig.json`, `vite.config.ts`, `vitest.config.ts`, `eslint.config.js`, `index.html`, `.env.example`, `.gitignore`, `src/main.tsx`, `src/App.tsx`, `src/index.css`, `src/vite-env.d.ts`, `src/lib/env.ts`, `src/lib/msalConfig.ts`, `src/lib/api.ts`, `src/auth/MsalProvider.tsx`, `src/auth/ProtectedRoute.tsx`, `src/auth/useAccessToken.ts`, `src/auth/ProtectedRoute.test.tsx`, `src/stores/authStore.ts`, `src/stores/chatStore.ts`, `src/stores/authStore.test.ts`, `src/pages/LoginPage.tsx`, `src/pages/ChatPage.tsx`, `src/pages/NotFoundPage.tsx`, `src/components/Spinner.tsx`, `src/test/setup.ts` | ~280 |
| 10 | FE Chat UI + WS client | `src/components/MessageBubble.tsx`, `src/components/MessageList.tsx`, `src/components/Composer.tsx`, `src/hooks/useChatWebSocket.ts`, `src/stores/chatStore.ts` (extend), `src/lib/api.ts` (extend), `src/pages/ChatPage.tsx` (replace placeholder), `src/components/MessageBubble.test.tsx`, `src/stores/chatStore.test.ts`, `src/hooks/useChatWebSocket.test.ts`, `src/pages/ChatPage.test.tsx`, `frontend/eslint.config.js` (add WebSocket globals) | ~530 production + ~380 tests |

**Slicing notes**:
- Slice 9 runs in parallel with slices 1–6 (no shared files; different folders).
- Slices 3 → 4 → 5 → 6 form a vertical slice (auth → repos → REST → WS+bridge) and MUST chain in order.
- Slices 7 and 8 depend on 5 + 6.
- Slice 2 carries the highest over-budget risk; `sdd-tasks` MUST forecast line counts and split into 2a / 2b if needed.

## 11. Open Questions (resolve in `sdd-apply` preflight)

- **Entra app registration values** (tenant ID, client ID, redirect URI, audience/scope) — needed in `.env.example` before slice 9 lands.
- **CORS**: dev = `*` per spec; prod list to be confirmed against the Static Web Apps hostname (release 2).
- **`example/001-support-agent.py`** is CLI-shaped with no streaming; the bridge's first integration test against the live SDK will be the only signal we have — budget half a day to debug if shapes drift (track under R1).
