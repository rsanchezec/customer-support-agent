# Archive Report: mvp-customer-support-chat (Release 1)

## Change Summary

| Field | Value |
|-------|-------|
| Change | mvp-customer-support-chat |
| Release | 1 (MVP) |
| Date Archived | 2026-06-15 |
| Artifact Store | openspec |
| Commits on Branch | 33 |

## Verification Summary

| Metric | Result |
|--------|-------|
| Backend Tests | 98/98 passing |
| Frontend Tests | 32/32 passing |
| Lint (ruff) | ✅ |
| Format | ✅ |
| Typecheck | ✅ |
| Build | ✅ |
| CRITICAL Issues | 0 |
| WARNING Issues | 8 (release-2 scope-deferred) |

## Archive Contents

- `proposal.md` ✅
- `design.md` ✅
- `tasks.md` ✅ (38/38 tasks complete)
- `specs/auth/spec.md` ✅
- `specs/chat-api/spec.md` ✅
- `specs/persistence/spec.md` ✅
- `specs/foundry-bridge/spec.md` ✅
- `specs/frontend/spec.md` ✅
- `specs/delivery/spec.md` ✅

## Delta Specs Synced to Main Specs

| Domain | Action |
|--------|--------|
| auth | Created |
| chat-api | Created |
| persistence | Created |
| foundry-bridge | Created |
| frontend | Created |
| delivery | Created |

## Slices and Commits

| # | Slice | Commit SHA | Subject |
|---|-------|------------|---------|
| 1 | BE bootstrap | 1306e38 | chore(backend): scaffold uv-managed FastAPI project with health endpoint, pytest, ruff |
| 2a | DB layer (engine + models) | fad634d | feat(db): add async SQLAlchemy engine, session dep, and domain models |
| 2b | DB layer (Alembic) | 0ee8d39 | feat(db): add Alembic migrations with 0001_init (users, conversations, messages) |
| 3 | Entra JWT validation | 67376d7 | feat(auth): add JWKS fetcher, user upsert, and get_current_user dependency |
| 4 | Repositories | 68388d0 | feat(foundry): add streaming service and chat turn orchestrator |
| 5 | REST endpoints | c35a346 | feat(api): add REST endpoints for conversation history |
| 6 | WS + Foundry bridge | e971fb7 | feat(chat): add WebSocket /ws/chat endpoint with subprotocol auth and streaming bridge |
| 7 | Backend tests | 1bb571f | feat(ws): acceptance tests for /ws/chat/{conversation_id} endpoint (slice 7.2) |
| 8 | Observability | 91376a8 | test(api): add REST endpoint acceptance tests (slice 8.2) |
| 9 | FE bootstrap | c365744 | feat(fe): add Vite + React 19 + TS + Tailwind v4 + MSAL React + Zustand skeleton |
| 10 | Chat UI + WS client | 80dfe3a | feat(fe): implement ChatGPT-style chat UI with streaming WebSocket client |
| Housekeeping | Spec sync + cleanup | 86f0eaf | docs(specs): sync 4 specs to match implementation |
| Re-verify | Final verification | 3a2aa3e | chore: close re-verify C3 and partial C6/C7 |

## Source of Truth Updated

- `openspec/specs/auth/spec.md`
- `openspec/specs/chat-api/spec.md`
- `openspec/specs/persistence/spec.md`
- `openspec/specs/foundry-bridge/spec.md`
- `openspec/specs/frontend/spec.md`
- `openspec/specs/delivery/spec.md`

## Release-2 Scope Deferred (8 WARNINGs)

1. **W1** — MAX_CONTENT_LENGTH = 8000 (spec: 4000)
2. **W2** — 422 for missing Authorization (spec: 401)
3. **W3** — no `code` field in 401
4. **W4** — no Spanish message in 401
5. **W5** — lost service session not handled
6. **W6** — Foundry error mapping not implemented
7. **W7** — `assistant.foundry_message_id` never set
8. **W8** — login uses `loginRedirect` not `loginPopup`

## Verification Report Reference

- **Topic Key**: `sdd/mvp-customer-support-chat/verify-report-3`
- **Observation ID**: 33
- **Verdict**: ARCHIVE-READY

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived. Ready for the next change.

**Next Recommended**: Start release 2 planning (containerization, Azure deployment, sidebar with multiple conversations).