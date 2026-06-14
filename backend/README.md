# Customer-Support Agent — Backend

## Quick Start

### Install dependencies

```bash
cd backend
uv pip install -r requirements.txt -r requirements-dev.txt --prerelease=allow
```

> **Note**: `agent-framework` is published as a prerelease on PyPI. The `--prerelease=allow` flag is required for `uv` to resolve it. Without the flag, the package is silently skipped.

### Run the development server

```bash
uv run uvicorn app.main:app --reload --port 8000
```

The API is live at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Run tests

```bash
uv run pytest
```

Note: slice 2a (engine + models + session) lands in one PR; the message-model roundtrip tests land in a follow-up PR (2a.2). Both are required for the DB layer to be considered complete.

Note: slice 4 (streaming + chat turn) lands in one PR; the chat turn roundtrip tests land in a follow-up PR (4.2). Both are required for the streaming layer to be considered complete.

### Lint and format check

```bash
uv run ruff check .
uv run ruff format --check .
```

## Environment variables

Copy `.env.example` to `.env` and fill in the values. The app reads `.env` automatically via `pydantic-settings`.

Key variables:
| Variable | Description |
|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Foundry project URL (from `example/.env`) |
| `AZURE_AI_AGENT_NAME` | Foundry agent name |
| `FOUNDRY_MODEL` | Model name (e.g. `gpt-5-mini`) |
| `DATABASE_URL` | Async database URL (SQLite for dev) |
| `CORS_ALLOWED_ORIGINS` | Comma-separated CORS origins |

## Project structure

```
backend/
├── app/
│   ├── main.py       # FastAPI app factory
│   ├── settings.py   # pydantic-settings configuration
│   └── api/
│       └── health.py # GET /healthz
├── tests/
│   ├── conftest.py   # pytest fixtures
│   └── test_health.py
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```
