# Proposal: MVP Customer-Support Chat

## Why
The Foundry `customer-support-agent` v1 (`gpt-5-mini`) exists, but external customers have no real way to talk to it: the only harness is `example/001-support-agent.py`, a one-shot CLI with no auth, no streaming, no persistence, and no UI. Support work is repeated manually, there is no conversation audit trail, and exposing the script as-is would leak Foundry credentials to the browser.

## What changes
A single-tenant web product: a FastAPI backend that brokers Foundry streaming over a JWT-authenticated WebSocket, and a Vite + React 19 client that lets a logged-in customer chat with the agent, streaming tokens in real time and resuming a single conversation across refresh.

## Impact
- **Users**: external customers of the company; one tenant; Rioplatense Spanish UI and system prompt (already in Foundry agent).
- **New dependencies**: FastAPI, uvicorn, SQLAlchemy 2.0 async, Alembic, aiosqlite (dev) / asyncpg (prod), PyJWT[crypto], httpx, pydantic-settings, structlog; Vite, React 19, TS, Tailwind v4, Zustand, MSAL React, vitest. Foundry stack mirrors `example/requirements.txt`. Backend env manager: `uv`.
- **New risks**: streaming API shape and Foundry thread/session shape are unverified; Entra JWKS availability; WS auth token leakage; CORS; multi-process WS without a session store; localStorage-only session (no cross-tab).

## Scope (release 1)

### In scope
- Entra ID login (MSAL React on FE, PyJWT JWKS validation on BE).
- One chat page; streaming tokens from the Foundry agent.
- Server-side persistence of one conversation per `user_id`; `thread_id` in `localStorage`; survives refresh and browser close.
- "Nueva conversación" button to start a fresh server-side thread.
- Backend tests with `pytest` + `pytest-asyncio`; frontend tests with `vitest`.

### Out of scope (release 1)
- Sidebar with multiple conversations.
- Containerization, Azure Container Apps, Static Web Apps, Postgres Flexible Server.
- Rate limiting, Redis, admin/monitoring view, multi-tenant isolation.

## Approach (release 1)
Ten slices. Each ≤ 400 changed lines (`delivery.strategy: force-chained`). Frontend skeleton (slice 9) runs in parallel with backend slices 1–6.

| # | Title | Scope | depends_on | ~lines | Key files |
|---|---|---|---|---|---|
| 1 | Backend bootstrap (uv + FastAPI) | `pyproject.toml`, `uv.lock`, FastAPI app, pydantic-settings, `.env` mirroring `example/.env`, `/healthz`. | — | 90 | `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/config.py`, `backend/.env` |
| 2 | DB layer (SQLAlchemy 2.0 async + Alembic) | async engine + session; `users`, `conversations`, `messages`; Alembic init + `0001_init`; `aiosqlite` for dev. | 1 | 200 | `backend/app/db/engine.py`, `backend/app/db/models.py`, `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_init.py` |
| 3 | Entra ID JWT validation | JWKS fetch+cache, PyJWT decode, `get_current_user` dep, OID→`users` upsert. | 2 | 160 | `backend/app/auth/jwks.py`, `backend/app/auth/deps.py`, `backend/app/auth/service.py` |
| 4 | Conversation + message repository | `create_or_resume`, `get_for_user`, `append_message`, `list_messages`. | 2 | 120 | `backend/app/repositories/conversations.py`, `backend/app/repositories/messages.py` |
| 5 | REST endpoints (non-streaming) | `POST /conversations`, `GET /conversations/{id}/messages`; 401 on bad/missing JWT. | 3, 4 | 110 | `backend/app/api/conversations.py`, `backend/app/api/messages.py`, `backend/app/api/deps.py` |
| 6 | WS endpoint + Foundry streaming bridge | `/ws/chat`; JWT in `Sec-WebSocket-Protocol`; FoundryAgent invocation with `stream=True`; persist user+assistant turns; broadcast deltas. **Streaming + thread shapes: verify in sdd-spec.** | 3, 4, 5 | 260 | `backend/app/ws/chat.py`, `backend/app/services/foundry_stream.py` |
| 7 | Backend tests (pytest + pytest-asyncio) | Scaffolding, fixtures, repository tests, auth-dep tests, WS handshake tests, REST shape tests. | 5, 6 | 220 | `backend/pytest.ini`, `backend/tests/conftest.py`, `backend/tests/test_repositories.py`, `backend/tests/test_auth.py`, `backend/tests/test_ws.py`, `backend/tests/test_api.py` |
| 8 | Backend observability + error mapping | structlog JSON logs; WS close codes; Spanish user-facing error messages. | 6, 7 | 140 | `backend/app/logging.py`, `backend/app/ws/errors.py`, `backend/app/api/errors.py` |
| 9 | FE bootstrap (Vite + React 19 + TS + Tailwind v4 + MSAL + Zustand) | Scaffold, MSAL provider, login page, chat store skeleton, layout shell. Parallel with slices 1–6. | — | 280 | `frontend/package.json`, `frontend/vite.config.ts`, `frontend/src/main.tsx`, `frontend/src/app/App.tsx`, `frontend/src/app/msal.ts`, `frontend/src/store/chat.ts`, `frontend/src/pages/Login.tsx`, `frontend/src/index.css` |
| 10 | Chat page + WS client + persistence hooks | Chat UI, native WebSocket client, `thread_id` in `localStorage`, resume on mount, "Nueva conversación". | 9, 6 | 320 | `frontend/src/pages/Chat.tsx`, `frontend/src/lib/ws.ts`, `frontend/src/lib/thread.ts`, `frontend/src/components/MessageBubble.tsx`, `frontend/src/components/Composer.tsx`, `frontend/tests/chat.test.ts` |

## Acceptance criteria
- `uv run uvicorn app.main:app` boots; `GET /healthz` → 200.
- `npm run dev` shows a login page; after Entra login the user lands on `/chat`.
- Sending a message streams tokens from the Foundry agent into the UI in real time.
- Refresh and full browser close preserve the same conversation; reopening loads its history.
- "Nueva conversación" creates a fresh server-side thread and clears the visible history.
- `pytest` and `npm test` (vitest) pass.
- `git diff --stat` for every slice ≤ 400 changed lines.

## Risks
| Risk | Likelihood | Mitigation owner | Slice |
|---|---|---|---|
| `FoundryAgent.run(stream=True)` signature differs from assumption | High | sdd-spec verifies against installed `agent_framework` version before slice 6 lands | 6 |
| Foundry `thread` / `AgentSession` shape unknown (cannot resume server-side conversation) | High | sdd-spec verifies; sdd-design documents fallback (recreate thread from `messages` history) | 6, 10 |
| Entra JWKS endpoint unreachable at startup or runtime | Med | JWKS cached with TTL; sdd-verify covers with a mock issuer | 3, 7 |
| WS auth token leaked via URL query string | High | sdd-spec: JWT only via `Sec-WebSocket-Protocol` subprotocol, never in URL | 6 |
| localStorage `thread_id` out of sync with server | Med | sdd-spec: server is source of truth; FE reconciles on connect | 5, 10 |
| `aiosqlite` accidentally used in prod | Low | Engine URL driven by env; sdd-design documents swap to `asyncpg` | 2 |
| Slice 2 (DB) blows the 400-line budget | Med | sdd-tasks forecasts; if High, split into 2a (engine + models) and 2b (Alembic + first migration) | 2 |

## Deferred to release 2
- Sidebar with multiple conversations (slice 11 in the explore plan).
- Containerization + Azure Container Apps (BE) + Static Web Apps (FE) + Postgres Flexible Server (slice 12).
- Per-user rate limit / Redis.
- Admin / monitoring view.
- Multi-tenant isolation.

## Open technical questions (resolve in sdd-spec)
1. Exact signature of `FoundryAgent.run(query, stream=True)` in `agent_framework.foundry` ≥ 1.8.0 — is the streamed object an `AgentRunResponseUpdate` with `.text` deltas, or a raw `ChatUpdate`? **Verify in sdd-spec.**
2. Shape of the `thread` / `AgentSession` object needed to reuse Foundry's server-side conversation across HTTP requests and WS reconnects. **Verify in sdd-spec.**
3. Concrete Entra ID app registration values (tenant ID, client ID, redirect URI) to embed in MSAL config (slice 9). **Verify in sdd-spec.**
4. Allowed CORS origins for the WS handshake in dev and prod. **Verify in sdd-design.**
