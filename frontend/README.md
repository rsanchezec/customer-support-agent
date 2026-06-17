# Customer Support Chat — Frontend

Vite + React 19 + TypeScript + Tailwind v4 + MSAL React + Zustand.

## Quick Start

```bash
# Install dependencies
npm install

# Copy and fill in your Entra App registration values
cp .env.example .env.local
# Edit .env.local with your VITE_ENTRA_TENANT_ID, VITE_ENTRA_CLIENT_ID

# Start dev server
npm run dev
# → http://localhost:5173
```

## Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Vite dev server on port 5173 |
| `npm run build` | Type-check and production build |
| `npm run preview` | Preview production build |
| `npm run test` | Run vitest tests (currently 1 smoke test) |
| `npm run lint` | ESLint checks |
| `npm run typecheck` | TypeScript type check |

## Entra App Registration

Fill in `.env.local` with values from your Azure Entra app registration:

```
VITE_ENTRA_TENANT_ID=<your-tenant-id>
# For a public demo with "Any Entra ID tenant + personal Microsoft accounts":
# VITE_ENTRA_AUTHORITY=https://login.microsoftonline.com/common
VITE_ENTRA_CLIENT_ID=<your-client-id>
VITE_ENTRA_API_SCOPE=api://<your-client-id>/access_as_user
VITE_ENTRA_REDIRECT_URI=http://localhost:5173
VITE_API_BASE_URL=http://localhost:8000
```

If `VITE_ENTRA_AUTHORITY` is omitted, the app signs users into the specific
tenant from `VITE_ENTRA_TENANT_ID`.

The app uses MSAL React with `loginRedirect`. After login it lands on `/chat`.

## Tech Stack

- **Vite 6** — build tool
- **React 19** — UI framework
- **TypeScript 5.6** — strict mode, Bundler module resolution
- **Tailwind v4** — CSS-first (no tailwind.config.ts)
- **MSAL React 3** — Entra ID authentication
- **Zustand 5** — lightweight state management
- **React Router 7** — client-side routing
- **Vitest 2** — unit/component tests with jsdom

## File Structure

```
src/
├── App.tsx              # Route definitions
├── main.tsx            # Entry point with MsalProvider
├── index.css           # Tailwind v4 entry
├── lib/
│   ├── env.ts          # Typed env var reader
│   ├── msalConfig.ts   # PublicClientApplication config
│   └── api.ts          # Fetch wrapper + conversation REST helpers
├── auth/
│   ├── MsalProvider.tsx
│   ├── ProtectedRoute.tsx
│   ├── useAccessToken.ts
│   └── *.test.tsx
├── stores/
│   ├── authStore.ts     # Zustand auth state (persisted)
│   ├── chatStore.ts     # Zustand chat state (optimistic messages, delta streaming)
│   └── *.test.ts
├── hooks/
│   ├── useChatWebSocket.ts  # WS client with reconnect backoff + message queue
│   └── *.test.ts
├── pages/
│   ├── LoginPage.tsx
│   ├── ChatPage.tsx     # Full chat UI with WS streaming
│   └── NotFoundPage.tsx
├── components/
│   ├── Spinner.tsx
│   ├── MessageBubble.tsx   # User/assistant bubbles with streaming spinner
│   ├── MessageList.tsx     # Auto-scroll message list
│   └── Composer.tsx        # Auto-resize textarea, Enter to send
└── test/
    └── setup.ts
```

## Current Test Count

- Slice 9: 2 component/store tests (ProtectedRoute, authStore)
- Slice 9.2: 1 smoke test (1 + 1 = 2)
- Slice 10: 31 component/unit tests (MessageBubble, chatStore, useChatWebSocket, ChatPage)
- Total: 34 tests
