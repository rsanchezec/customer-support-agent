# Customer Support Agent

Aplicación de chat de atención al cliente construida sobre **Microsoft Foundry** (Azure AI Agent Service). Permite que usuarios autenticados conversen con un agente de IA en tiempo real, con streaming token a token, persistencia de conversaciones y autenticación multi-tenant mediante Microsoft Entra ID.

El proyecto está compuesto por un backend FastAPI (Python 3.12) y un frontend React 19 + Vite. La comunicación principal se realiza por WebSocket para el streaming y por REST para la gestión de conversaciones. La especificación funcional del sistema se describe bajo el flujo **Spec-Driven Development (SDD)** en `openspec/specs/`.

---

## Tabla de contenidos

1. [Stack tecnológico](#stack-tecnológico)
2. [Arquitectura de alto nivel](#arquitectura-de-alto-nivel)
3. [Estructura del proyecto](#estructura-del-proyecto)
4. [Flujos clave](#flujos-clave)
5. [Setup local](#setup-local)
6. [Variables de entorno](#variables-de-entorno)
7. [Comandos útiles](#comandos-útiles)
8. [Testing](#testing)
9. [Arquitectura interna](#arquitectura-interna)
10. [Despliegue](#despliegue)
11. [Convenciones de contribución](#convenciones-de-contribución)
12. [Licencia](#licencia)

---

## Stack tecnológico

### Backend (`backend/`)

| Capa | Tecnología | Versión |
|---|---|---|
| Lenguaje | Python | `>=3.12` (ver `pyproject.toml`) |
| Framework HTTP | FastAPI | `>=0.115.0` |
| Servidor ASGI | Uvicorn | `>=0.32.0` |
| Validación y settings | Pydantic / pydantic-settings | `2.12.4` / `>=2.6.0` |
| ORM async | SQLAlchemy | `>=2.0.0` (con `aiosqlite`) |
| Driver SQLite async | aiosqlite | `>=0.20.0` |
| Migraciones | Alembic | `>=1.13` |
| Foundry SDK | `azure-ai-projects` | `>=2.2.0` |
| Agent Framework | `agent-framework` | `>=1.8.0` (prerelease) |
| Credenciales Azure | `azure-identity` (`DefaultAzureCredential`) | última estable |
| JWT | `PyJWT[crypto]` | `>=2.8` |
| Cliente HTTP async | `httpx` | `>=0.27` |
| Tests | `pytest`, `pytest-asyncio`, `pytest-mock` | `>=8.3.0` / `>=0.24.0` / `>=3.14.0` |
| Linter / format | `ruff` | `>=0.8.0` |

### Frontend (`frontend/`)

| Capa | Tecnología | Versión |
|---|---|---|
| Build | Vite | `^6.0.0` |
| UI | React + React DOM | `^19.0.0` |
| Lenguaje | TypeScript | `^5.6.0` (modo estricto) |
| Routing | React Router | `^7.0.0` |
| Estilos | Tailwind CSS (CSS-first, sin `tailwind.config.ts`) | `^4.0.0` |
| Auth | `@azure/msal-react` + `@azure/msal-browser` | `^3.0.0` / `^4.0.0` |
| Estado | Zustand | `^5.0.0` |
| Tests | Vitest + Testing Library + jsdom | `^2.0.0` / `^16.0.0` / `^25.0.0` |
| Linter | ESLint 9 + `typescript-eslint` | `^9.0.0` / `^8.0.0` |

> El frontend usa el alias `@/*` para apuntar a `frontend/src/*` (configurado en `vite.config.ts` y `tsconfig.json`).

---

## Arquitectura de alto nivel

```
                        ┌──────────────────────────┐
                        │  Browser (React 19 SPA)  │
                        │  Vite + MSAL React       │
                        └────────────┬─────────────┘
                                     │
                ┌────────────────────┼────────────────────┐
                │ REST (HTTPS)       │ WebSocket (WSS)     │
                │ Authorization:     │ Sec-WebSocket-      │
                │ Bearer <jwt>      │ Protocol: bearer.jwt
                ▼                    ▼
        ┌───────────────────────────────────────────────┐
        │  FastAPI backend (Python 3.12)                │
        │  • Routers: /healthz, /conversations,         │
        │    /ws/chat/{conversation_id}                 │
        │  • Auth deps: PyJWT + JWKS (TTL 600s)         │
        │  • Services: User, Conversation, ChatTurn,    │
        │    FoundryStream                              │
        └──────────┬─────────────────────────┬──────────┘
                   │                         │
                   ▼                         ▼
        ┌──────────────────┐       ┌────────────────────┐
        │  SQLAlchemy 2.x  │       │  Azure AI Foundry  │
        │  + aiosqlite     │       │  AIProjectClient   │
        │  (dev)           │       │  + FoundryAgent    │
        │  users /         │       │  gpt-5-mini        │
        │  conversations / │       │  (default model)   │
        │  messages        │       └────────────────────┘
        └──────────────────┘
                   │
                   ▼
        ┌──────────────────┐
        │  Entra ID (JWKS) │
        │  login.microsoft  │
        │  online.com       │
        └──────────────────┘
```

**Notas de la arquitectura**

- En **desarrollo** la base de datos es SQLite (archivo `backend/app.db`, modo WAL, FK enforcement).
- En **producción** la URL de base de datos se intercambia por un `postgresql+asyncpg://...` sin cambios de esquema (`openspec/specs/persistence/spec.md`).
- El cliente Foundry (`AIProjectClient`) y la `AzureCliCredential` se instancian una sola vez en el `lifespan` de FastAPI y se reutilizan en todas las requests.
- La `DefaultAzureCredential` soporta cadena de credenciales (`az login`, variables de entorno, Managed Identity, etc.).

---

## Estructura del proyecto

```
customer-support-agent/
├── backend/                    # API FastAPI (Python 3.12)
│   ├── alembic/                # Migraciones de esquema
│   │   ├── env.py              #   Alembic async (lee DATABASE_URL de Settings)
│   │   └── versions/0001_init.py  # users / conversations / messages
│   ├── app/
│   │   ├── main.py             # create_app() + lifespan (JwksFetcher, FoundryClient, ConversationService)
│   │   ├── settings.py         # pydantic-settings: Foundry, Entra, DB, CORS
│   │   ├── api/
│   │   │   ├── health.py       #   GET /healthz
│   │   │   ├── auth/
│   │   │   │   ├── deps.py     #     Bearer deps, get_current_user, decode_and_validate_token
│   │   │   │   └── jwks_fetcher.py  # JWKS client con TTL 600s
│   │   │   ├── rest/
│   │   │   │   ├── conversations.py  # CRUD /conversations
│   │   │   │   └── schemas.py        # Pydantic v2 (ConversationOut, MessageOut, etc.)
│   │   │   └── websockets/
│   │   │       └── chat.py     # WS /ws/chat/{conversation_id} con auth por subprotocol
│   │   ├── db/
│   │   │   ├── base.py         # Declarative base
│   │   │   ├── engine.py       # AsyncEngine + PRAGMA WAL/foreign_keys
│   │   │   └── session.py      # async_sessionmaker + dep get_session
│   │   ├── domain/             # Modelos SQLAlchemy 2.x (User, Conversation, Message)
│   │   └── services/
│   │       ├── foundry.py            # FoundryClient (wrapper de AIProjectClient)
│   │       ├── foundry_stream.py     # FoundryStreamService (patrón canónico SDK 1.8.0+)
│   │       ├── chat_turn.py          # ChatTurnService (orquesta persistencia + stream)
│   │       ├── conversation_service.py  # CRUD de conversaciones
│   │       ├── user_service.py       # Upsert por Entra OID
│   │       ├── stream_events.py      # StreamDelta / StreamFinal / StreamError
│   │       ├── text_sanitizer.py     # Limpieza de marcadores de citación
│   │       └── agent_cache.py        # Cache in-process de AgentVersionDetails
│   ├── tests/                  # pytest (asyncio_mode=auto)
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── alembic.ini
│   └── .env.example
│
├── frontend/                   # SPA React 19
│   ├── src/
│   │   ├── main.tsx            #   Bootstrap + MsalProviderInstance + BrowserRouter
│   │   ├── App.tsx             #   Rutas: /login, /chat (ProtectedRoute), /
│   │   ├── auth/
│   │   │   ├── MsalProvider.tsx       # Wrapper con initialize()
│   │   │   ├── ProtectedRoute.tsx     # Redirige a /login si no autenticado
│   │   │   └── useAccessToken.ts      # acquireTokenSilent + fallback redirect
│   │   ├── lib/
│   │   │   ├── env.ts          #   Lector tipado de import.meta.env
│   │   │   ├── msalConfig.ts   #   PublicClientApplication + loginRequest.scopes
│   │   │   └── api.ts          #   apiFetch + listConversations / getConversation / createConversation
│   │   ├── stores/             # Zustand
│   │   │   ├── authStore.ts    #   user (persistido en localStorage `auth-user`)
│   │   │   └── chatStore.ts    #   threadId, messages, wsStatus, conversationId
│   │   ├── hooks/
│   │   │   └── useChatWebSocket.ts  # WS con subprotocol bearer.jwt + backoff exponencial
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx   # Botón "Iniciar sesión con Microsoft" (loginRedirect)
│   │   │   ├── ChatPage.tsx    # Header + MessageList + Composer
│   │   │   └── NotFoundPage.tsx
│   │   ├── components/
│   │   │   ├── MessageList.tsx # Auto-scroll + estados vacíos
│   │   │   ├── MessageBubble.tsx  # Burbuja user/assistant + spinner streaming
│   │   │   ├── Composer.tsx    # Textarea auto-resize, Enter envía
│   │   │   └── Spinner.tsx
│   │   └── test/setup.ts       # Vitest + jest-dom
│   ├── package.json
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   ├── tsconfig.json
│   ├── eslint.config.js
│   └── .env.example
│
├── openspec/                   # Especificación funcional (SDD)
│   ├── config.yaml             #   Reglas de SDD y delivery (force-chained, 400 líneas/PR)
│   ├── specs/                  #   Specs por capacidad (auth, chat-api, delivery, foundry-bridge, frontend, persistence)
│   └── changes/archive/        #   Cambios cerrados y archivados
│
├── example/                    # Scripts de referencia para Foundry SDK
│   ├── 001-support-agent.py    #   Invoke single-shot
│   ├── 002-batman-agent-streaming.py  # Patrón canónico de streaming
│   └── .env                    #   Plantilla de variables Foundry
│
├── README.md                   # Este archivo
└── .atl/                       # (interno, ignorar)
```

---

## Flujos clave

### 1. Autenticación (Entra ID + JWKS)

```
[Browser]                   [MSAL React]              [FastAPI]                  [Entra ID]
    │                            │                        │                          │
    │ 1. Click "Iniciar sesión"  │                        │                          │
    ├───────────────────────────▶│                        │                          │
    │                            │ 2. loginRedirect()     │                          │
    ├────────────────────────────┼───────────────────────▶│                          │
    │                            │                        │ 3. Auth code + PKCE      │
    │                            │                        ├─────────────────────────▶│
    │                            │                        │◀─────── id_token + code ─┤
    │ 4. Redirect /chat          │ 5. acquireTokenSilent  │                          │
    │◀───────────────────────────┤    (access_token)      │                          │
    │                            │                        │                          │
    │ 6. Request REST/WS         │                        │                          │
    │   Authorization: Bearer    │                        │                          │
    ├────────────────────────────┼───────────────────────▶│                          │
    │                            │                        │ 7. Validar firma con JWKS│
    │                            │                        │    (cache TTL 600s)      │
    │                            │                        │ 8. Verificar aud / iss   │
    │                            │                        │ 9. Extraer oid + email   │
    │                            │                        │ 10. user_service.upsert  │
    │◀────── 200 / WS open ─────┼────────────────────────┤                          │
```

**Puntos clave**

- El frontend **nunca** envía el token en query string ni en cookies: la SPA usa el header `Authorization: Bearer ...` en REST y el subprotocolo `bearer.jwt.<token>` en WebSocket.
- El backend acepta un set configurable de `aud` e `iss` (`ENTRA_ALLOWED_AUDIENCES`, `ENTRA_ALLOWED_ISSUERS`) para escenarios multi-tenant y para MSAs personales en desarrollo (`openspec/specs/auth/spec.md`).
- Si la JWKS falla, el backend intenta las variantes v1/v2 del endpoint `https://login.microsoftonline.com/{tenant}/discovery/keys` antes de devolver `401`.

### 2. Ciclo de chat (streaming)

```
[User]   [Composer]  [chatStore]  [WS]         [FastAPI]                  [Foundry]
  │          │            │          │               │                          │
  │ 1. Type  │            │          │               │                          │
  ├─────────▶│            │           │              │                          │
  │          │ 2. submit  │           │              │                          │
  │          ├───────────▶│ addOpt..  │              │                          │
  │          │            │ + send()  │              │                          │
  │          │            ├──────────▶│ 3. JSON      │                          │
  │          │            │           │  {content}   │                          │
  │          │            │           ├─────────────▶│ 4. ChatTurnService       │
  │          │            │           │              │   • persist user msg     │
  │          │            │           │              │   • FoundryStreamService │
  │          │            │           │              ├─────────────────────────▶│
  │          │            │           │              │                          │
  │          │            │           │ 5. delta     │ ◀─── chunk 1 ────────────┤
  │          │            │           │◀─────────────┤                          │
  │          │ 6. render  │ appendDelta│              │                          │
  │          │◀───────────┤           │              │                          │
  │          │            │           │   ...        │                          │
  │          │            │           │ 7. delta     │ ◀─── chunk N ────────────┤
  │          │            │           │◀─────────────┤                          │
  │          │            │           │ 8. done      │ ◀── get_final_response ──┤
  │          │            │           │◀─────────────┤   • link foundry_session │
  │          │            │           │              │   • persist asst msg     │
  │          │ 9. final   │ replaceContent + completeMessage                   │
  │          │◀───────────┤           │              │                          │
```

**Protocolo WebSocket**

- **Subprotocol**: el cliente abre con `["bearer.jwt", "jwt.<token>"]`; el navegador los concatena como `bearer.jwt.<token>`. El backend extrae el token y selecciona el subprotocol `bearer.jwt` para confirmar.
- **Trama de entrada** (`{content, metadata}`): `content` es el texto del usuario; `metadata` es siempre `null` (campo reservado para uso futuro).
- **Tramas de salida**:
  - `{ "type": "delta", "text": "<chunk>" }` — fragmento incremental
  - `{ "type": "done", "conversation_id": "...", "foundry_conversation_id": "...", "text": "<full>" }` — frame final, marca el cierre de un turno
  - `{ "type": "error", "code": "<code>", "message": "<es>" }` — error recuperable (conexión se mantiene) o terminal (conexión cerrada)

**Persistencia** (contrato en `app/services/chat_turn.py`):

1. El mensaje del usuario se inserta y se hace `commit` **antes** de invocar Foundry (si el stream falla, el turno del usuario queda registrado).
2. Cada `delta` NO se persiste. Solo se reenvía por WS.
3. El mensaje del assistant se inserta **una sola vez** al recibir el `StreamFinal` (texto agregado).
4. Si el stream falla, no se inserta ninguna fila `assistant`.
5. `conversations.foundry_conversation_id` se enlaza en el primer turno y se reutiliza en los siguientes (patrón `agent.get_session(service_session_id=...)`).

### 3. Manejo de errores

| Código (target spec) | Origen | Comportamiento actual |
|---|---|---|
| `empty_message` | Validación en WS | El handler cierra con `1008` y envía `{type:"error", code:"bad_request", message:"content must be a non-empty string"}` |
| `message_too_long` | `> MAX_CONTENT_LENGTH` (8000 chars en WS) | Cierra con `1008`, `code: "bad_request"` |
| `conversation_not_found` | ID ajeno al usuario o inexistente | REST devuelve `404` con `detail: "conversation not found"`; en WS el frame es `bad_request` |
| `foundry_transient` | 5xx / 429 / timeout de Foundry | `FoundryStreamService.stream_chat` emite un `StreamError`; el WS envía `{type:"error", code:"stream_error"}` |
| `foundry_auth` | Credenciales inválidas | Mismo path: `stream_error` con mensaje de la excepción |
| `foundry_payload` | 4xx de Foundry | Mismo path: `stream_error` |
| `agent_not_found` | `get_version` falla | Mismo path: `stream_error`; agente cacheado con `reset()` solo en tests |
| `internal` | Excepción no manejada en WS | `{type:"error", code:"internal"}` + `close(1011)` |
| `unauthenticated` | Token ausente / inválido en WS | Cierra con `1008` antes del `accept()` |

> **Nota**: el spec define los códigos `foundry_*` como identificadores estables. La implementación actual los agrupa bajo `stream_error` con el mensaje original; ver `openspec/specs/foundry-bridge/spec.md` para los criterios de mapeo que se aplicarán cuando se refinen los catch handlers.

---

## Setup local

### Prerrequisitos

- **Python 3.12+** (el `pyproject.toml` declara `requires-python = ">=3.12"`).
- **Node.js 20+** y **npm**.
- **uv** (`pip install uv` o `winget install astral-sh.uv`).
- **Azure CLI** autenticado (`az login`) si vas a usar Foundry con `DefaultAzureCredential`.
- Un **proyecto de Microsoft Foundry** con un agente publicado (mínimo: nombre + versión).
- Una **App Registration** en Entra ID con:
  - Tipo: Single-page application
  - Redirect URI: `http://localhost:5173` (dev)
  - Permiso delegado: `api://<client-id>/access_as_user` (scope) expuesto por la **misma** app o por la API si está separada

### Backend

```bash
cd backend

# 1. Crear venv e instalar dependencias (incluye agent-framework prerelease)
uv sync --prerelease=allow

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env con FOUNDRY_PROJECT_ENDPOINT, ENTRA_TENANT_ID, ENTRA_CLIENT_ID, etc.

# 3. Aplicar migraciones (crea ./app.db con users / conversations / messages)
uv run alembic upgrade head

# 4. Arrancar el servidor de desarrollo
uv run uvicorn app.main:app --reload --port 8000
```

La API queda en `http://localhost:8000`. La documentación interactiva está en `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend

# 1. Instalar dependencias
npm install

# 2. Configurar variables de entorno
cp .env.example .env.local
# Editar .env.local con VITE_ENTRA_TENANT_ID, VITE_ENTRA_CLIENT_ID, VITE_ENTRA_API_SCOPE

# 3. Arrancar Vite (puerto 5173)
npm run dev
```

La aplicación queda en `http://localhost:5173`. Tras autenticarte con Entra, te redirige a `/chat`.

> **Importante**: el frontend deriva la URL del WebSocket a partir de `VITE_API_BASE_URL` reemplazando `http` por `ws`. No hace falta una variable aparte para el WS.

---

## Variables de entorno

### Backend (`backend/.env`)

Las variables se cargan vía `pydantic-settings` desde `.env` (ver `app/settings.py`).

| Variable | Descripción | Ejemplo | Requerido |
|---|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Endpoint del proyecto Foundry | `https://<name>.services.ai.azure.com/api/projects/<proj>` | Sí |
| `AZURE_AI_AGENT_NAME` | Nombre lógico del agente desplegado | `customer-support-agent` | Sí |
| `AGENT_VERSION` | Versión del agente. Vacío = tomar la última publicada | `1` | No |
| `FOUNDRY_MODEL` | Modelo del agente (referencia, lo lee el cliente Foundry) | `gpt-5-mini` | No (default `gpt-5-mini`) |
| `ENTRA_TENANT_ID` | Tenant ID de Entra (para construir la JWKS URI) | `11111111-2222-3333-4444-555555555555` | Sí |
| `ENTRA_CLIENT_ID` | Application (client) ID de la SPA | `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee` | Sí |
| `ENTRA_APP_AUDIENCE` | Audience esperado en el JWT (típicamente `api://<client-id>`) | `api://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee` | Sí |
| `ENTRA_ALLOWED_AUDIENCES` | Lista CSV de audiences adicionales (MSAs personales, multi-tenant) | `api://other-app,api://dev` | No |
| `ENTRA_ALLOWED_ISSUERS` | Lista CSV de issuers aceptados además de los v1/v2 por defecto | `https://sts.windows.net/<tenant>/` | No |
| `CORS_ALLOWED_ORIGINS` | Lista CSV de orígenes permitidos para CORS | `http://localhost:5173,https://app.example.com` | No (default `["http://localhost:5173"]`) |
| `APP_ENV` | Entorno lógico; activa `echo` de SQLAlchemy cuando es `dev` | `dev` | No |
| `DATABASE_URL` | URL async de SQLAlchemy | `sqlite+aiosqlite:///./app.db` | No |

### Frontend (`frontend/.env.local`)

El lector tipado está en `frontend/src/lib/env.ts`. Todas las variables deben llevar el prefijo `VITE_` para ser expuestas al cliente.

| Variable | Descripción | Ejemplo | Requerido |
|---|---|---|---|
| `VITE_ENTRA_TENANT_ID` | Tenant ID de Entra | `11111111-2222-3333-4444-555555555555` | Sí |
| `VITE_ENTRA_CLIENT_ID` | Application (client) ID de la SPA | `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee` | Sí |
| `VITE_ENTRA_API_SCOPE` | Scope delegado que la SPA solicita al hacer login | `api://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/access_as_user` | Sí |
| `VITE_ENTRA_REDIRECT_URI` | URI de retorno (debe coincidir con la app registration) | `http://localhost:5173` | No (default `http://localhost:5173`) |
| `VITE_API_BASE_URL` | URL base del backend (REST y WS) | `http://localhost:8000` | No (default `http://localhost:8000`) |

> El `VITE_API_BASE_URL` se usa tanto para `fetch()` (REST) como para construir la URL del WebSocket (`http` → `ws`, `https` → `wss`).

---

## Comandos útiles

### Backend

```bash
# Tests
uv run pytest                                # Toda la suite
uv run pytest tests/api                      # Solo API (auth + REST + WS)
uv run pytest tests/services                 # Solo lógica de negocio
uv run pytest -k "test_chat_turn"            # Filtrar por nombre

# Lint / format
uv run ruff check .
uv run ruff format --check .
uv run ruff format .

# Migraciones
uv run alembic upgrade head                  # Aplicar
uv run alembic downgrade -1                  # Rollback de la última
uv run alembic revision --autogenerate -m "msg"  # Generar nueva migración

# Servidor dev
uv run uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
# Desarrollo
npm run dev              # Vite dev server (puerto 5173)
npm run build            # tsc -b + vite build
npm run preview          # Servir el build localmente

# Calidad
npm run typecheck        # tsc --noEmit
npm run lint             # ESLint
npm run test             # Vitest (jsdom, setupFiles en src/test/setup.ts)
```

---

## Testing

| Capa | Framework | Ubicación | Cobertura actual |
|---|---|---|---|
| Backend (auth deps) | `pytest` | `backend/tests/api/test_deps.py` | Validación JWT (válido, expirado, firma incorrecta), JWKS multi-tenant, `get_current_user` |
| Backend (JWKS) | `pytest` | `backend/tests/api/test_jwks_fetcher.py` | TTL, refetch, `reset()` |
| Backend (REST) | `pytest` | `backend/tests/api/rest/test_conversations.py` | `list / get / create / patch / delete`, scoping por usuario |
| Backend (WS) | `pytest` | `backend/tests/api/websockets/test_chat_endpoint.py` | Handshake con subprotocol, auth failure (`1008`) |
| Backend (services) | `pytest` | `backend/tests/services/test_*.py` | `FoundryClient`, `FoundryStreamService`, `ChatTurnService`, `ConversationService`, `Settings` |
| Backend (modelos) | `pytest` | `backend/tests/db/test_*_model.py` | Roundtrip de `User`, `Conversation`, `Message` |
| Backend (Alembic) | `pytest` | `backend/tests/db/test_alembic.py` | Migración `0001_init` aplica a una DB vacía |
| Frontend (store) | `vitest` | `frontend/src/stores/chatStore.test.ts` + `authStore.test.ts` | Mutaciones del store, persistencia |
| Frontend (hook) | `vitest` | `frontend/src/hooks/useChatWebSocket.test.ts` | Connect, deltas, `done`, `error`, backoff, no reconnect en `1008` |
| Frontend (componentes) | `vitest` + RTL | `frontend/src/components/MessageBubble.test.tsx` | Renderizado user/assistant, estados |
| Frontend (páginas) | `vitest` + RTL | `frontend/src/pages/ChatPage.test.tsx` | Hidratación, retry, `localStorage` |
| Frontend (auth) | `vitest` + RTL | `frontend/src/auth/ProtectedRoute.test.tsx` | Redirect a `/login` |

**Áreas bien cubiertas**: ciclo de vida de conversaciones (REST + WS), validación JWT, reconciliación de threads, cliente WS con backoff.

**Áreas con cobertura limitada o no automatizada**:

- Tests E2E reales contra Foundry (el SDK se mockea en todos los tests de servicios).
- Pruebas de carga / concurrencia sobre el WS (un solo cliente por turno).
- Pruebas de CORS en runtime (la config se valida por tests unitarios indirectos).
- CI automatizada: la release 1 se entrega sin pipeline (`openspec/specs/delivery/spec.md` lo declara explícitamente).

Los fixtures de test del backend usan SQLite en memoria con `aiosqlite` y mockean `AIProjectClient` y JWKS, de modo que ningún test golpea Entra ni Foundry real.

---

## Arquitectura interna

### Backend — servicios principales

```
┌──────────────────────────────────────────────────────────────────┐
│  app/main.py                                                     │
│  create_app() → lifespan construye y guarda en app.state:        │
│    • jwks_fetcher: JwksFetcher                                   │
│    • foundry_client: FoundryClient                               │
│    • conversation_service: ConversationService                   │
└──────────────────────────────────────────────────────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌──────────────────┐  ┌──────────────────┐  ┌────────────────────┐
│ api/auth/deps.py │  │ api/rest/         │  │ api/websockets/    │
│  get_current_user│  │  conversations.py│  │  chat.py           │
│  (Bearer JWT)    │  │  (CRUD)          │  │  (streaming)       │
└──────────────────┘  └──────────────────┘  └────────────────────┘
        │                       │                       │
        └─────────┬─────────────┴─────────────┬─────────┘
                  │                           │
                  ▼                           ▼
        ┌──────────────────┐        ┌──────────────────────┐
        │ services/        │        │ services/            │
        │  user_service.py │        │  chat_turn.py        │
        │  (upsert por OID)│        │  (orquesta 1 turno)  │
        └──────────────────┘        └─────────┬────────────┘
                                              │
                                              ▼
                                    ┌──────────────────────┐
                                    │  foundry_stream.py   │
                                    │  FoundryStreamService│
                                    │  (SDK 1.8.0+ pattern)│
                                    └──────────┬───────────┘
                                               │
                                               ▼
                                    ┌──────────────────────┐
                                    │  foundry.py          │
                                    │  FoundryClient       │
                                    │  (AIProjectClient)   │
                                    └──────────────────────┘
```

**Responsabilidades**

- **`FoundryClient`** (`app/services/foundry.py`): wrapper del `AIProjectClient` + `DefaultAzureCredential`. Crea el cliente lazy, expone `get_existing_agent()` (con cache in-process via `agent_cache.get_or_resolve`), `invoke()` single-shot y `aclose()` para el `lifespan`. Una sola instancia por proceso.
- **`FoundryStreamService`** (`app/services/foundry_stream.py`): aplica el patrón canónico del SDK 1.8.0+ (`agent.run(input, stream=True, session=session)`) y emite un flujo de `StreamEvent` (delta / final / error). Si no hay `service_session_id` crea uno nuevo; si lo hay, llama `agent.get_session(service_session_id=...)` para reusar el contexto. Implementación deliberadamente simple (~85 líneas) tras el refactor de `47555c5`.
- **`ChatTurnService`** (`app/services/chat_turn.py`): orquesta el ciclo completo de un turno. Persiste el mensaje del usuario antes del run; enlaza `foundry_conversation_id` tras el primer `StreamFinal`; ofrece `persist_assistant_message()` para que el WS handler guarde la respuesta agregada al final. Es la **única fuente de verdad para la persistencia** durante un turno.
- **`ConversationService`** (`app/services/conversation_service.py`): CRUD de conversaciones con scoping por usuario (`get_or_create`, `list_for_user`, `set_title`, `link_foundry_session`). Lanza `ConversationNotFoundError` si el id pertenece a otro usuario.
- **`UserService`** (`app/services/user_service.py`): upsert de `users` por `entraid_oid`. Crea la fila en el primer login y actualiza `email` en logins sucesivos.
- **`JwksFetcher`** (`app/api/auth/jwks_fetcher.py`): cliente de la JWKS de Entra con cache en memoria y TTL configurable (default 600s). `aclose()` cierra el `httpx.AsyncClient` subyacente.
- **WebSocket handler** (`app/api/websockets/chat.py`): valida el subprotocol, autentica al usuario, resuelve la conversación, itera los eventos del `ChatTurnService` y los serializa al cliente. Mantiene la conexión abierta entre turnos (loop con `websocket.receive_json()`).
- **REST handlers** (`app/api/rest/conversations.py`): `GET /conversations`, `POST /conversations`, `GET /conversations/{id}`, `PATCH /conversations/{id}`, `DELETE /conversations/{id}`. Validación Pydantic v2 en `schemas.py`.

### Frontend — capas

```
┌──────────────────────────────────────────────────────────────────┐
│  main.tsx → MsalProviderInstance → BrowserRouter → App           │
└──────────────────────────────────────────────────────────────────┘
                                  │
                ┌─────────────────┼─────────────────┐
                ▼                 ▼                 ▼
        ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
        │ /login       │  │ /chat        │  │ /*           │
        │ LoginPage    │  │ ChatPage     │  │ NotFoundPage │
        └──────────────┘  └──────┬───────┘  └──────────────┘
                                 │
                                 ▼
                        ┌────────────────┐
                        │  MessageList   │  ← useChatStore.messages
                        │  Composer      │  ← llama sendMessage()
                        └────────────────┘
                                 │
                                 ▼
                        ┌────────────────────────┐
                        │ useChatWebSocket       │
                        │  • connect / send      │
                        │  • backoff exponencial │
                        │  • handlers delta/done │
                        │  • no reconnect en 1008│
                        └────────────────────────┘
```

**Responsabilidades**

- **`useChatStore`** (`src/stores/chatStore.ts`): estado transient de chat. `messages[]` con status (`sending | sent | streaming | failed`), `wsStatus` (`idle | connecting | open | disconnected | failed`), `conversationId`, `foundryConversationId`. Acciones: `addOptimisticUserMessage`, `appendDelta` (inmutable, concatena al message existente o crea uno nuevo con id `stream-<ts>`), `replaceMessageContent`, `completeMessage`, `failMessage`, `clearChat`.
- **`useAuthStore`** (`src/stores/authStore.ts`): wrapper Zustand con `persist` middleware; guarda `user: AccountInfo` en `localStorage` bajo la clave `auth-user`.
- **`useChatWebSocket`** (`src/hooks/useChatWebSocket.ts`): fábrica de WebSocket inyectable (`WebSocketFactory` por defecto = `new WebSocket(...)`). Reconnect con backoff `min(2^attempt * 1s, 30s)`, hasta 5 intentos. Cola de mensajes en memoria si el socket no está abierto. No reconnect en `1008` (auth) ni `1011` (server error). Cierra limpio con `1000` en `close()`.
- **`ChatPage`** (`src/pages/ChatPage.tsx`): entry point del flujo autenticado. Adquiere token con `acquireAccessToken`, hidrata o crea conversación con `createConversation` / `getConversation`, conecta el WS. Expone un botón "Nueva conversación" que limpia el store y reabre el WS. Renderiza `MessageList` y `Composer`.
- **`MessageList`** (`src/components/MessageList.tsx`): auto-scroll a la última burbuja, estados vacíos según `wsStatus`.
- **`MessageBubble`** (`src/components/MessageBubble.tsx`): burbuja con burbuja-pulso durante streaming, botón "Reintentar" en estado `failed`. Aplica `cleanContent()` (helper local) para descartar glifos de citación que Foundry puede emitir.
- **`Composer`** (`src/components/Composer.tsx`): textarea auto-resize, `maxLength=4000`, `Enter` envía (con Shift+Enter para salto de línea). Disabled cuando `wsStatus !== "open"`.
- **`api.ts`** (`src/lib/api.ts`): `apiFetch()` genérico (inyecta `Authorization`), `ApiError` con `code` + `status`, helpers `listConversations / getConversation / createConversation`.
- **`msalConfig.ts`** (`src/lib/msalConfig.ts`): `PublicClientApplication` con `cacheLocation: "localStorage"` y `loginRequest.scopes = [VITE_ENTRA_API_SCOPE]`.
- **`useAccessToken.ts`** (`src/auth/useAccessToken.ts`): `acquireTokenSilent`; si lanza `InteractionRequiredAuthError`, hace fallback a `acquireTokenRedirect`.

### Convenciones de contrato BE ↔ FE

- **Pydantic ↔ TypeScript**: los esquemas en `app/api/rest/schemas.py` están espejados manualmente en `frontend/src/lib/api.ts` (`ConversationOut`, `MessageOut`, `ConversationDetailOut`). El cambio de `snake_case` (BE) a `camelCase` (FE) NO es automático: los nombres se mantienen en `snake_case` en las interfaces TS (e.g. `foundry_conversation_id`, `created_at`) para coincidir con el JSON que devuelve FastAPI.
- **Identificadores**: UUID v4 como `string` en TS (no se parsea a `UUID` en el cliente).
- **Fechas**: `string` ISO 8601 con zona horaria. No se formatean en el cliente.
- **Roles de mensaje**: `Literal["user", "assistant"]` en Python se traduce a `"user" | "assistant"` en TS.

---

## Despliegue

> Esta sección documenta el deploy real del demo: frontend en Vercel y backend en Render. Reemplaza las recomendaciones genéricas de Azure que estaban en versiones anteriores del README.

### Opciones consideradas

| Opción | Costo | Pros | Contras | Decisión |
|---|---|---|---|---|
| **Azure App Service B1** | ~$13/mes (prorrateado a horas) | Integración nativa con Entra, red abierta, WebSockets OK, Managed Identity sin secretos, control fino sobre el plan | Costo mensual fijo incluso para un demo, requiere tarjeta de crédito y suscripción Azure activa | **Rechazado para el demo**. Viable como target de producción si el proyecto continúa |
| **Render.com (Free)** | $0/mes | HTTPS automático, deploy desde GitHub, soporta WebSockets, env vars por UI, health checks | Sleep a los 15 min de inactividad, cold start ~30s, almacenamiento efímero (SQLite se pierde) | **Elegido para el backend del demo** |
| **Fly.io (Free)** | $0/mes (con créditos limitados) | Máquinas cerca del usuario, WebSockets, `fly secrets` por CLI | Free tier cambió de política varias veces, sleep también, menos familiar para el equipo | No seleccionado — Render ya cubre lo necesario |
| **Railway.app** | $5 crédito/mes (después se cobra por uso) | Deploy simple, soporta procesos largos, buen DX | $5 crédito alcanza solo para un servicio muy ligero, requiere tarjeta | No seleccionado — Render es $0 y suficiente |

### Decisión final: Vercel (FE) + Render (BE)

**Frontend en Vercel.** Vercel es ideal para una SPA Vite: build automático desde GitHub, CDN global, HTTPS automático, dominio `*.vercel.app` gratuito, y variables de entorno expuestas al cliente vía prefijo `VITE_`. No hay servidor que mantener ni procesos que reiniciar.

**Backend NO en Vercel.** Vercel Functions es serverless con timeout máximo de 60s en plan hobby y no soporta conexiones WebSocket de larga duración. El backend de este proyecto mantiene un socket abierto por turno de chat, así que Vercel queda descartado para el BE.

**Backend en Render.** Render permite correr un proceso Uvicorn continuo, soporta WebSockets, y tiene health checks que reaniman el servicio tras el sleep. El free tier es $0/mes, suficiente para un demo de 1-2 semanas. La limitación principal es el sleep a los 15 min (mitigable con un ping externo cada 10-14 minutos).

### Frontend en Vercel — paso a paso

1. **Crear el proyecto en Vercel**
   - Ir a [vercel.com/new](https://vercel.com/new).
   - "Import Git Repository" → autorizar GitHub → seleccionar `customer-support-agent`.
   - **Project Name**: `customer-support-agent` (define el subdominio `*.vercel.app`).
2. **Configurar el build**
   - **Root Directory**: `frontend` (editar desde el selector "Edit" al lado del campo; este paso es el que más se olvida).
   - **Build Command**: `npm run build` (default de Vite).
   - **Output Directory**: `dist` (default de Vite).
   - **Install Command**: `npm install` (default).
3. **Setear las variables de entorno** (sección "Environment Variables"):

| Key | Value (demo actual) | Descripción |
|---|---|---|
| `VITE_ENTRA_TENANT_ID` | `4922a12a-f1fd-40bc-affe-c63dc44acc33` | Tenant de Entra |
| `VITE_ENTRA_CLIENT_ID` | `85b8f05c-7a9e-4c18-bfd0-281a5521c391` | Client ID del App Registration del FE |
| `VITE_ENTRA_API_SCOPE` | `api://customer-support-agent/access_as_user` | Scope delegado que pide MSAL al hacer login |
| `VITE_ENTRA_REDIRECT_URI` | `https://customer-support-agent-omega.vercel.app` | Debe coincidir exactamente con el Redirect URI configurado en el App Registration |
| `VITE_API_BASE_URL` | `https://customer-support-agent-api-1h5k.onrender.com` | URL del backend en Render (sin slash final) |

   Marcar las casillas **Production**, **Preview** y **Development** para que apliquen a los tres entornos.

4. **Crear `frontend/vercel.json`** para que las rutas de React Router no devuelvan 404 al refrescar (`/chat/abc-123` debe servir `index.html` y dejar que el router resuelva):

   ```json
   {
     "rewrites": [
       { "source": "/(.*)", "destination": "/index.html" }
     ]
   }
   ```

5. **Deploy**. Click "Deploy". Vercel clona el repo, instala, ejecuta `npm run build` y publica el bundle en la CDN. Builds típicos tardan 40-60s.
6. **Deploys automáticos**. Cada `git push` a `main` dispara un deploy de producción. Los PRs desde otras ramas generan deploys de preview con URL propia (útil para QA antes de mergear).
7. **URL final**: `https://customer-support-agent-omega.vercel.app`.

### App Registration del Frontend en Microsoft Entra ID

La SPA de Vercel se autentica contra esta App Registration. Datos del demo actual:

- **Nombre**: `Customer Support Agent - Frontend`
- **Application (client) ID**: `85b8f05c-7a9e-4c18-bfd0-281a5521c391`
- **Directory (tenant) ID**: `4922a12a-f1fd-40bc-affe-c63dc44acc33`
- **Application ID URI**: `api://customer-support-agent` (URI custom legible, no el GUID default)
- **Scope expuesto**: `api://customer-support-agent/access_as_user`
  - **Who can consent**: `Admins and users` (permite que cualquier usuario del tenant haga consent sin intervención de un admin)
  - **Admin consent display name**: `Access Customer Support Agent API`
  - **Admin consent description**: `Allow the app to access the Customer Support Agent API on behalf of the signed-in user`
- **Redirect URI (Single-page application)**: `https://customer-support-agent-omega.vercel.app`

**Pasos para crearlo en Azure Portal** (Microsoft Entra ID → App registrations → New registration):

1. **Name**: `Customer Support Agent - Frontend`. Supported account types: `Accounts in this organizational directory only` (single tenant).
2. **Redirect URI**: platform `Single-page application`, valor `https://customer-support-agent-omega.vercel.app`. Guardar.
3. **Expose an API** → "Set the Application ID URI" → reemplazar el `api://<guid>` default por `api://customer-support-agent`.
4. **Expose an API** → "Add a scope":
   - Scope name: `access_as_user`
   - Who can consent: `Admins and users`
   - Admin consent display name / description: los de arriba.
5. **API permissions**: ya viene con `User.Read` de Microsoft Graph por default. No requiere Grant admin consent porque el scope `access_as_user` se expone a sí mismo.
6. (Opcional) **Authentication** → agregar también `http://localhost:5173` como Redirect URI SPA para desarrollo local.

### Backend en Render — paso a paso

1. **Crear el Web Service**
   - Ir a [dashboard.render.com](https://dashboard.render.com) → New → Web Service.
   - "Connect a repository" → autorizar GitHub → seleccionar `customer-support-agent`.
2. **Configurar el servicio**
   - **Name**: `customer-support-agent-api`
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**:
     ```bash
     alembic upgrade head && uvicorn app.main:create_app --factory --host 0.0.0.0 --port $PORT
     ```
     El `&&` es deliberado: si las migraciones fallan, uvicorn NO arranca y Render detecta el fallo y reintenta el deploy, en lugar de servir una app con esquema desactualizado que crashea en la primera query.
   - **Instance Type**: `Free`
   - **Health Check Path**: `/healthz`
3. **Setear las variables de entorno** (sección "Environment"):

| Key | Value de ejemplo | Descripción |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | `https://<name>.services.ai.azure.com/api/projects/<proj>` | Endpoint del proyecto Foundry (copiar de "Project details" en el portal de Foundry) |
| `AZURE_AI_AGENT_NAME` | `customer-support-agent` | Nombre del agente publicado en Foundry |
| `AGENT_VERSION` | *(vacío)* | Vacío = tomar la última versión publicada automáticamente |
| `FOUNDRY_MODEL` | `gpt-5-mini` | Modelo de referencia (lo lee el cliente Foundry) |
| `APP_ENV` | `prod` | Desactiva el `echo` de SQLAlchemy |
| `DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | Para el demo alcanza con SQLite; ver advertencia sobre disco efímero abajo |
| `ENTRA_TENANT_ID` | `4922a12a-f1fd-40bc-affe-c63dc44acc33` | Tenant de Entra (para construir la JWKS URI) |
| `ENTRA_CLIENT_ID` | `85b8f05c-7a9e-4c18-bfd0-281a5521c391` | Client ID de la SPA (se usa como audience) |
| `ENTRA_APP_AUDIENCE` | `api://customer-support-agent` | Audience esperado en el JWT |
| `CORS_ALLOWED_ORIGINS` | `https://customer-support-agent-omega.vercel.app` | Único origen permitido en producción |
| `AZURE_TENANT_ID` | `4922a12a-f1fd-40bc-affe-c63dc44acc33` | Tenant para `ClientSecretCredential` (mismo que la SPA) |
| `AZURE_CLIENT_ID` | `<service-principal-client-id>` | Client ID del SP `customer-support-agent-backend` (ver sección siguiente) |
| `AZURE_CLIENT_SECRET` | `<service-principal-secret>` | Secret del SP (ver sección siguiente) |

4. **Deploy**. Click "Create Web Service". Render clona el repo, instala dependencias, aplica migraciones y arranca uvicorn. El primer deploy tarda 2-3 min (instalación de `agent-framework` prerelease + `azure-ai-projects`).
5. **URL final**: `https://customer-support-agent-api-1h5k.onrender.com`.

> El flag `--factory` le dice a uvicorn que llame a `create_app()` para obtener la instancia, en lugar de buscar un símbolo `app` a nivel de módulo. Esto es necesario porque `create_app` toma un `Settings` opcional y la forma factoría permite override en tests.

### Service Principal para Foundry

En local, `az login` provee las credenciales que `DefaultAzureCredential` usa para hablar con Foundry. En Render no hay sesión interactiva: hay que darle al backend un Service Principal (SP) con permisos explícitos sobre el proyecto Foundry.

**Crear el SP en Azure Portal**:

1. **App registrations** → New registration:
   - **Name**: `customer-support-agent-backend`
   - **Supported account types**: `Accounts in this organizational directory only` (single tenant)
   - **Redirect URI**: dejar vacío (es un SP, no un cliente interactivo).
2. **Certificates & secrets** → New client secret:
   - **Description**: `render-deploy-2026-06` (con fecha para trackear rotaciones)
   - **Expires**: 90 días (recomendado; rotar antes de que expire)
   - **Copiar el `Value` del secret** (no el `Secret ID`). Una vez que se cierra el panel, el value no se vuelve a mostrar.
3. **Asignar el rol sobre el proyecto Foundry**:
   - Ir al recurso del Foundry project en el portal de Azure.
   - **Access Control (IAM)** → **Add role assignment**.
   - **Role**: `Azure AI Developer` (o `Azure AI User` si el primero no aparece en la suscripción).
   - **Members**: buscar `customer-support-agent-backend` y seleccionarlo.
   - **Review + assign**.

**Las 3 env vars resultantes** van en la sección Environment de Render (ya listadas en la tabla anterior como `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`). `DefaultAzureCredential` las detecta y arma un `ClientSecretCredential` automáticamente, sin código adicional.

### Issues encontrados durante el deploy (y cómo se resolvieron)

Cronología de los bugs que aparecieron al llevar el código desde local a Render, y los fixes aplicados:

**1. `alembic upgrade head` falla con `ModuleNotFoundError: No module named 'app'`**

Causa: Alembic no encontraba el paquete `app` para importar los modelos durante la migración. El `cwd` de Render para el comando de build es `backend/` (gracias a Root Directory), pero `alembic.ini` no estaba agregando ese directorio al `sys.path` de Python.

Fix: en `backend/alembic.ini` ya existía la línea `prepend_sys_path = .` (línea 12), pero estaba comentada con `#` por default. Se descomentó y Alembic pasó a prepender el directorio actual al `sys.path` antes de importar `app.*`.

**2. `create_app() missing 1 required positional argument: 'settings'`**

Causa: el start command de Render usaba `uvicorn app.main:create_app --factory`, que invoca la factoría sin pasarle argumentos. La firma original era `create_app(settings: Settings)` (sin default), por lo que la llamada fallaba en runtime.

Fix: hacer `settings` opcional con default `None`, y dentro de la función instanciar `Settings()` si llega como `None` (ver `app/main.py` líneas 23-26). Esto permite usar la factoría tanto en producción (sin args, lee de env vars) como en tests (con un `Settings` mockeado).

**3. `ENTRA_ALLOWED_AUDIENCES` no se leía del environment**

Causa: `pydantic-settings` mapea el nombre de la variable al nombre del field por convención snake_case → UPPER_SNAKE. El field "lógico" del código se llama `entra_allowed_audiences` (porque expone una `@property` que parsea el string CSV en una lista), pero pydantic intentaba leer `ENTRA_ALLOWED_AUDIENCES` como un `list[str]`, no como el raw string CSV. El parseo silenciosamente se ignoraba y la variable quedaba vacía en runtime, así que la validación de JWT rechazaba audiences válidos.

Fix: agregar un field interno `entra_allowed_audiences_raw: str = Field(default="", validation_alias="ENTRA_ALLOWED_AUDIENCES")` que lee el string crudo, y mantener la `@property` `entra_allowed_audiences` que lo parsea en lista. Mismo patrón aplicado a `entra_allowed_issuers` (ver `app/settings.py` líneas 50-55).

**4. JWKS fetch falla con `HTTPStatusError` repetido en Render**

Síntoma: las requests al backend empezaban a tirar `httpx.HTTPStatusError` al intentar refrescar la JWKS cada hora (TTL del cache). Tras varios minutos con errores, Render suspendía el servicio.

Causa: el plan free de Render impone un umbral de tráfico "service-initiated" (outbound originado en el servicio, no en respuestas a requests de usuarios). El fetch periódico de JWKS contra `login.microsoftonline.com` cruza ese umbral y Render marca el servicio como excedido y lo suspende. Doc: <https://render.com/docs/free#service-initiated-traffic-threshold>.

**5. Solución: JWKS hardcodeado como fallback + retry con backoff exponencial**

Refactor de `JwksFetcher` (`app/api/auth/jwks_fetcher.py`) con estrategia de 3 niveles:

1. **Live fetch con retry**: `httpx.AsyncClient` reutilizado (uno por fetcher, no por request como antes), 3 intentos con backoff `(1s, 2s, 4s)`.
2. **Fallback a snapshot pinneada en JSON**: si los 3 intentos fallan, se sirve una snapshot guardada en `backend/app/api/auth/jwks_snapshot.json` (cargada al import del módulo). Las claves no son secretos — son públicas, están en el endpoint de discovery — pero pinnerlas evita el hit saliente que dispara el rate limit de Render.
3. **TTL extendido en fallback**: una vez en modo fallback, no se reintenta el live fetch durante 5 minutos (constante `_FALLBACK_TTL_SECONDS`) para no cruzar el umbral de Render.

Resultado: el servicio sigue respondiendo incluso cuando Render bloquea el outbound. La única forma de que el backend devuelva `401` por este motivo es que Microsoft haya rotado las signing keys y la snapshot pinneada esté desactualizada (ver Operación continua para el refresh).

### Operación continua

#### Refresh del JWKS snapshot

**Por qué hay una snapshot en JSON**: el JWKS se guarda en `backend/app/api/auth/jwks_snapshot.json` (no inline en el `.py`) para que sea fácil de revisar en `git diff` cuando se refresca. Las claves son públicas — están en el endpoint de discovery de Microsoft — pero las pinneamos en código para evitar el rate limit de Render free tier.

**Cuándo refrescar**: Microsoft rota las signing keys del tenant cada ~6 semanas. Pasado ese tiempo, la snapshot pinneada queda desactualizada y los JWT nuevos se firman con un `kid` que no está en la snapshot. El síntoma es: el frontend autentica OK (MSAL hace su parte), pero el backend devuelve `401 InvalidSignatureError` con un `kid` distinto al de la snapshot. En el log de Render aparecerán líneas tipo `JWKS live fetch failed after 3 attempts; using bundled snapshot (N keys)`.

**Cómo refrescar** (5 minutos, todo desde local):

```bash
# 1. Traés el JWKS actualizado de Microsoft y sobreescribís el JSON
python example/fetch_jwks.py --write
#    Output:
#      Fetched 5 key(s) from tenant 4922a12a-...
#      Wrote snapshot to backend/app/api/auth/jwks_snapshot.json

# 2. Revisás qué cambió (diff humano, antes de commitear)
git diff backend/app/api/auth/jwks_snapshot.json
#    Si ves líneas verdes con kid nuevo → MS agregó una key
#    Si ves líneas rojas → MS sacó una key
#    Si no ves nada → no hay cambios, no sigas

# 3. Si te cierra el cambio, commiteás y pusheás
git commit -am "chore(be): refresh JWKS snapshot"
git push origin main
#    Render auto-detecta el push y redeploya (~1 min)
```

**El JSON tiene un header `_comment`** con metadata (tenant ID, timestamp del último refresh) que se preserva entre runs — útil para diffs y para que el reviewer entienda cuándo se actualizó.

**Atajos de `fetch_jwks.py`**:

- Sin flags: imprime el JSON raw a stdout (para inspección ad-hoc).
- `--write`: actualiza el snapshot file en el path default.
- `--snapshot <path>`: override del path (útil si querés un snapshot alternativo o de testing).
- `<tenant_id>` posicional: override del tenant default (el de customer-support-agent).

Para un demo de 1-2 semanas, es poco probable que haga falta.

#### Onboarding de usuarios (quién puede usar el chat)

El acceso al chat está controlado por Microsoft Entra ID en el lado del FE. El BE no maneja registro de usuarios — solo valida los JWTs que el FE le manda. Así que la respuesta a "¿quién puede entrar?" vive 100% en Azure.

**Setup actual**: la app registration del FE (`Customer Support Agent - Frontend`) está configurada como **"Single tenant — My organization only"**. Eso significa que **solo usuarios que ya existan en tu tenant** (`4922a12a-f1fd-40bc-affe-c63dc44acc33`) pueden loguearse.

Hay dos formas de dar acceso:

##### Opción A — Agregar usuarios específicos al tenant (single-tenant)

Útil si querés controlar uno por uno quién entra.

1. **Azure Portal** → **Microsoft Entra ID** → **Users** → **+ New user**.
2. Elegí tipo:
   - **Create new user** → para gente de tu organización. Llenas email, nombre, password auto-generada.
   - **Invite external user** → para gente de otra empresa. Les llega un mail con link de aceptación, pueden usar su cuenta Microsoft existente.
3. Una vez que el usuario tiene cuenta en tu tenant, puede ir a `https://customer-support-agent-omega.vercel.app` y loguearse.

##### Opción B — Multi-tenant (recomendado para el demo)

Más fácil para demos: cualquier persona con cuenta Microsoft (work, school o personal como @outlook.com / @hotmail.com) puede entrar sin que tengas que agregarla a tu tenant.

1. **Azure Portal** → **App registrations** → **`Customer Support Agent - Frontend`** → **Authentication**.
2. En **"Supported account types"**, cambiá de "Single tenant" a una de:
   - **Multitenant** → solo cuentas de organizaciones registradas en Entra ID (excluye cuentas personales tipo @outlook.com).
   - **Multitenant and personal Microsoft accounts** → cualquiera, incluidas cuentas personales. Es la opción más abierta.
3. **Save**. Listo. Ya pueden entrar.
4. **El BE no necesita cambios**: el `aud` del token sigue siendo `api://customer-support-agent`, que ya está en `ENTRA_ALLOWED_AUDIENCES` del backend.

##### Comparación y recomendación

| | Opción A (single-tenant) | Opción B (multi-tenant) |
|---|---|---|
| **Setup por usuario** | Manual cada vez | Una vez y todos entran |
| **Para demo a N clientes** | Tedioso si N > 3 | Una vez, escalás a cualquier N |
| **Para producción** | Más seguro, controlado | Requiere Conditional Access, MFA, allowlist, etc. |
| **Audit de quién entró** | Cada usuario es nativo del tenant | Necesita layer extra (Application Insights, log analytics) |

**Recomendación para el demo actual**: Opción B con **"Multitenant and personal Microsoft accounts"**. Setup de 30 segundos, todos los clientes pueden probar con su propia cuenta. Después del demo, si querés cerrar el acceso, volvés a "Single tenant" en el mismo panel.

#### Rotar el `AZURE_CLIENT_SECRET` del SP

**Cuándo**: cada 90 días (vencimiento por default del secret) o antes si el secret quedó expuesto en un log, screenshot, chat, commit, etc. La rotación no requiere recrear el SP: solo se genera un secret nuevo y se reemplaza el viejo.

**Cómo**:

1. Azure Portal → App registrations → `customer-support-agent-backend` → Certificates & secrets → New client secret. **Expires**: 180 días (o lo que requiera la política de la organización).
2. Copiar el `Value` del nuevo secret.
3. Render → `customer-support-agent-api` → Environment → editar `AZURE_CLIENT_SECRET`, pegar el nuevo valor, Save. Render redeploya automáticamente.
4. Una vez verificado que el nuevo secret funciona (login + chat OK), eliminar el secret viejo desde el mismo panel (botón "..." → Delete) para no acumular credenciales activas.

#### Apagar / eliminar el Web Service de Render

Cuando termine el demo, conviene liberar el servicio (el plan Free no cobra, pero Render sigue manteniendo el slot reservado y puede mandar reminders de "servicio inactivo"):

- **Suspender temporalmente**: Settings → "Suspend Service". El servicio queda pausado, no se cobra nada, y se puede reanudar desde la misma pantalla. Los datos en disco (SQLite) se pierden al suspender.
- **Eliminar definitivamente**: Settings → "Delete Service" → escribir el nombre del servicio para confirmar. El slot se libera y el subdominio `*.onrender.com` deja de resolver. La acción es irreversible.

> **Importante**: SQLite en Render free vive en almacenamiento efímero. Al suspender, redesplegar o cambiar de plan, `app.db` se borra y los usuarios pierden el historial de conversaciones. Para un demo de 1-2 semanas es aceptable; para algo más serio, migrar a un Postgres externo (Neon, Supabase, Azure Postgres) y actualizar `DATABASE_URL` a `postgresql+asyncpg://...`.

#### Cold starts en Render free

Render free pone el servicio a dormir tras 15 minutos sin tráfico entrante. La primera request después de ese período tarda ~30 segundos en "despertar" (Render la mantiene esperando mientras arranca el proceso, pero el cliente ve un timeout o un error 502/504 si su timeout HTTP es menor a 30s).

Mitigaciones posibles:

- **Ping externo cada 10-14 minutos** desde un cron (UptimeRobot gratis, GitHub Actions con `cron`, etc.) contra `/healthz`. El servicio nunca duerme y los cold starts desaparecen. Trade-off: el servicio siempre activo consume un poco más del free tier.
- **Aceptar el cold start** como parte del demo: la primera interacción muestra un spinner con "Reconectando…", el `useChatWebSocket` del FE tiene backoff exponencial y reintenta solo.

Para una demo en vivo, abrir el chat 1-2 minutos antes de la presentación para evitar el primer-arranque frío en vivo frente al cliente.

---

## Convenciones de contribución

- **Conventional Commits** para los mensajes (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`). Ver `git log --oneline` para ejemplos.
- **No** incluir `Co-Authored-By` ni ningún tipo de atribución de IA en los commits.
- **No** añadir badges de CI ni configuración de pipelines: la release 1 se entrega sin CI (cada chained PR es la auditoría).
- **Force-chained delivery**: cada PR debe pesar como máximo 400 líneas contra la base branch. Si una tarea lo excede, se divide antes de mergear.
- **Una tarea por concern**: persistencia, auth, streaming y UI viven en slices separados y rara vez se tocan en el mismo PR.
- **Mensajes de error al usuario** en español neutro profesional (`openspec/specs/auth/spec.md`, `chat-api/spec.md`). El `code` permanece en inglés como identificador estable.
- **Tests antes de merge**: el slice solo se considera completo cuando la suite local pasa (`uv run pytest`, `npm run test`).
- **Specs primero**: cualquier cambio de comportamiento se inicia como `openspec/changes/<slug>/{proposal,specs,design,tasks}.md` y solo se implementa después de `sdd-archive`.

### Estructura de un PR

```
Title:  <conventional commit message>

Body:
  • Why: problema o motivación
  • What: resumen de los cambios
  • Spec: link al change en openspec/changes/ (si aplica)
  • Test: comandos corridos y resultado
  • Risk: notas para el revisor (migraciones, breaking changes, etc.)
```

---

## Licencia

MIT — ver `LICENSE` (TBD: añadir el archivo `LICENSE` en la raíz del repositorio).

