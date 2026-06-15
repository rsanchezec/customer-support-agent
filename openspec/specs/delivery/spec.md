# Delivery Specification

## Purpose
Defines the testing scaffolding and the release-1 delivery constraints. Release 1 ships without a CI pipeline; both backend and frontend MUST have a working local test command (`pytest`, `npm test`) before any slice merges. Each slice is bounded to 400 changed lines per PR (force-chained).

## Requirements

### Requirement: Backend test runner
The backend MUST use `pytest` + `pytest-asyncio` with `asyncio_mode = auto`. The first BE-touching slice MUST add both dependencies to `pyproject.toml` and a minimal `tests/conftest.py`.

#### Scenario: Run all backend tests
- GIVEN `uv run pytest` from `backend/`
- WHEN pytest runs
- THEN exit code is `0` and every test under `tests/` is discovered.

### Requirement: Backend test fixtures
`conftest.py` MUST provide an in-memory SQLite engine per test, an `AsyncSession` fixture, a mock `AIProjectClient`, and a fake JWKS issuer. Tests MUST NOT hit real Entra or real Foundry.

#### Scenario: Isolated DB and mocked Foundry
- GIVEN a test exercises the chat handler
- WHEN it runs
- THEN the engine points at `sqlite+aiosqlite:///:memory:`, data is torn down on exit, and the bridge returns a deterministic `ResponseStream` with no network call.

### Requirement: Backend critical-path coverage
Tests MUST cover: JWT auth dep (valid / expired / bad signature), repository (create / resume / append / list / ownership), REST shapes (status codes, JSON), and WS handshake (success / auth failure / subprotocol echo).

#### Scenario: Auth rejects bad token
- GIVEN a token signed by a wrong key
- WHEN the dep runs
- THEN it raises `401` with `code = "invalid_token"`.

#### Scenario: Repo blocks cross-user access
- GIVEN user A and user B each own a conversation
- WHEN user A calls `repo.get_for_user(user_a_id, conv_b_id)`
- THEN the function returns `None`.

#### Scenario: WS rejects missing subprotocol
- GIVEN a client opens `/ws/chat` with no subprotocol
- WHEN the handshake runs
- THEN the server closes with `1008`.

### Requirement: Backend linter and formatter
The backend MUST use `ruff` for linting and formatting, configured in `pyproject.toml`. `uv run ruff check .` and `uv run ruff format --check .` MUST both pass before a slice lands. `mypy` is optional in release 1.

### Requirement: Frontend test runner
The frontend MUST use `vitest` + `@testing-library/react` with `jsdom`. `npm test` MUST discover every test under `frontend/tests/`.

#### Scenario: Run all frontend tests
- GIVEN `npm test`
- WHEN vitest runs
- THEN exit code is `0`.

### Requirement: Frontend critical-path coverage
Tests MUST cover: chat store (append-delta, replace-on-done, clear-on-new), WS client (connect with subprotocol, reconnect on `1006`, no-reconnect on `1008`, token never in URL), and thread reconciliation (resume on mount, mint-new on 404).

#### Scenario: Store appends delta immutably
- GIVEN one assistant message `"Hola"`
- WHEN `appendDelta(" mundo")` dispatches
- THEN the message is `"Hola mundo"` and the previous reference is not mutated.

#### Scenario: WS client never puts token in URL
- GIVEN a valid access token
- WHEN the URL is built
- THEN `URL.search` is empty and `protocols` contains `bearer.<jwt>`.

### Requirement: No CI in release 1
The repository MUST NOT include GitHub Actions, Azure Pipelines, or any CI config in release 1. Chained PRs are the audit trail; CI is deferred to release 2.

#### Scenario: No CI directory
- GIVEN the end of slice 10
- WHEN a developer inspects the repo
- THEN there is no `.github/workflows/`, no `azure-pipelines.yml`, and no CI badge.

### Requirement: Force-chained delivery, 400-line budget
Every slice MUST be ≤ 400 changed lines against the base branch. Over-budget slices MUST be split before merge.

#### Scenario: Slice 2 over budget
- GIVEN slice 2 forecasts at 480 lines
- WHEN sdd-tasks runs
- THEN it splits into 2a (engine + models) and 2b (Alembic + first migration), each as its own chained PR.
