# Frontend Specification

## Purpose
Defines the Vite + React 19 + TypeScript + Tailwind v4 client that authenticates with Entra ID via MSAL React, opens a WebSocket to the backend, and renders a streaming chat UI in neutral professional Spanish. The active thread id persists in `localStorage` across refresh.

## Requirements

### Requirement: Vite + React 19 + TypeScript + Tailwind v4 scaffold
The frontend MUST be a Vite project with React 19, TypeScript (strict), Tailwind v4, Zustand, and MSAL React. `npm run dev` MUST serve on `http://localhost:5173`.

#### Scenario: Fresh clone boots
- GIVEN `npm install && npm run dev`
- WHEN the dev server starts
- THEN `http://localhost:5173` renders the login screen.

### Requirement: Entra ID login via MSAL React
The frontend MUST use `MsalProvider` to drive an interactive popup login against the configured Entra app. On success, the `accessToken` MUST be available to the WS client and REST callers.

#### Scenario: First-time login
- GIVEN an unauthenticated user on `/`
- WHEN they click "Iniciar sesión con Microsoft"
- THEN MSAL opens Entra; on success the user lands on `/chat` and the token is cached.

#### Scenario: Silent refresh
- GIVEN the cached refresh token is valid and the access token is within 5 minutes of expiry
- WHEN MSAL checks
- THEN it acquires a new access token silently.

#### Scenario: Login failure
- GIVEN the user cancels or types wrong credentials
- WHEN MSAL returns an error
- THEN the UI shows "No pudimos iniciar sesión. Probá de nuevo." and stays on the login page.

### Requirement: Chat page layout
The chat page MUST render: a top bar with user identity and "Nueva conversación", a scrollable list (user right, assistant left), and a sticky composer. All copy is neutral professional Spanish.

#### Scenario: Empty chat on first load
- GIVEN a fresh conversation id
- WHEN the page renders
- THEN the list shows: "Hola, soy el agente de soporte. ¿En qué te puedo ayudar?".

### Requirement: WebSocket client
The frontend MUST use the native `WebSocket` API, connect to `wss://<api-host>/ws/chat` (or `ws://` in dev), authenticate via the `bearer.<jwt>` subprotocol, and reconnect with exponential backoff on transient failures. The token MUST NEVER appear in the URL.

#### Scenario: Connect with valid token
- GIVEN a non-expired access token
- WHEN the page mounts
- THEN the client opens the WS with `Sec-WebSocket-Protocol: bearer.<jwt>` and accepts the echo.

#### Scenario: Reconnect on `1006`
- GIVEN a transient network drop
- WHEN the WS closes with `1006`
- THEN the client waits `min(2^attempt, 30)s` and reconnects, up to 5 attempts.

#### Scenario: No reconnect on `1008`
- GIVEN the WS closes with `1008`
- WHEN the client handles it
- THEN it does NOT auto-reconnect and redirects to the login page.

#### Scenario: Token never in URL
- GIVEN any code path opens the WS
- WHEN the URL is built
- THEN `URL.search` is empty and the token appears ONLY in the subprotocol.

### Requirement: `thread_id` persistence in `localStorage`
The active `conversation_id` MUST be stored under a versioned key (e.g., `csa:thread_id:v1`). On mount, the client MUST attempt to resume; on 404 it MUST mint a new conversation via `POST /conversations`.

#### Scenario: Resume on refresh
- GIVEN `localStorage` has `csa:thread_id:v1 = "c-uuid"`
- WHEN the page mounts
- THEN the client calls `GET /conversations/c-uuid/messages` and hydrates.

#### Scenario: Stale id reconciled
- GIVEN the server returns 404
- WHEN resume fails
- THEN the client clears the stale id, calls `POST /conversations`, and stores the new id.

### Requirement: Client store (Zustand)
The frontend MUST hold transient chat state: `threadId`, `messages[]`, `isStreaming`, `error`. Appending a delta MUST NOT replace the whole message array.

#### Scenario: Append delta immutably
- GIVEN the last assistant message is `"Hola"`
- WHEN `appendDelta(" mundo")` dispatches
- THEN the message becomes `"Hola mundo"` and the rest of the array is unchanged.
