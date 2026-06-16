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

> La release 1 no incluye pipeline de CI ni IaC (ver `openspec/specs/delivery/spec.md`). Esta sección describe el target, no un proceso automatizado.

### Backend — opciones recomendadas

- **Azure Container Apps** o **Azure App Service (Linux, Python 3.12)**. Imagen basada en `python:3.12-slim` con `uv` instalado; comando de arranque: `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- **Managed Identity** asignada al recurso para que `DefaultAzureCredential` se autentique contra Foundry sin secretos. Eliminar `az login` del flujo de runtime.
- **Variables de entorno** configuradas vía App Settings (App Service) o secretos de Container Apps. `DATABASE_URL` apunta al driver async de la base de datos destino.
- **Base de datos**:
  - Dev: SQLite (`sqlite+aiosqlite:///./app.db`) con WAL + FK enforcement.
  - Prod: `postgresql+asyncpg://<user>:<pwd>@<host>:5432/<db>` (Azure Database for PostgreSQL Flexible Server recomendado). El esquema no requiere cambios; las migraciones se aplican con `uv run alembic upgrade head` desde un job de release o como `command` en el contenedor.

### Frontend — opciones recomendadas

- **Azure Static Web Apps** o **Azure App Service (Linux, Node static)**. Build: `npm ci && npm run build`. Artefacto: `frontend/dist/`.
- `VITE_API_BASE_URL` debe apuntar al HTTPS público del backend.
- Configurar el **redirect URI** de la App Registration para que coincida con el dominio de producción.

### Foundry

- El proyecto Foundry debe tener publicado el agente (`customer-support-agent` o el nombre que se pase en `AZURE_AI_AGENT_NAME`) con al menos una versión estable.
- El `FOUNDRY_PROJECT_ENDPOINT` se copia desde la página "Project details" del portal de Foundry.
- La identidad del backend (Managed Identity o service principal de `az login`) debe tener rol **Azure AI User** (o equivalente) sobre el proyecto.

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

