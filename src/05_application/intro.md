# 05_application — Introduction

This folder contains the complete user-facing layer of the RagRats system: a Python API server and a Next.js web frontend. Everything before this step (preprocessing, retrieval, generation) runs offline or via CLI. This step is what makes the system interactive — a user opens a browser, logs in, types a question, and gets an answer powered by the full RAG pipeline.

---

## Overview of the two parts

```
05_application/
├── api/          Python backend (FastAPI + uvicorn)
└── web/          TypeScript frontend (Next.js + React + Tailwind CSS)
```

The two halves run as separate processes and communicate over HTTP. During development, the frontend runs on port 3000 and the backend on port 8001. The frontend proxies all `/api/` requests to the backend so the browser only ever talks to one origin.

---

## The Stack

### Backend: FastAPI

FastAPI is a modern Python web framework built on top of Starlette (the ASGI server toolkit) and Pydantic (data validation). It was chosen for several reasons:

- It integrates naturally with Python's type hints, which the existing codebase already uses heavily.
- It uses Pydantic models for request/response validation, meaning malformed JSON is rejected automatically before it reaches any handler.
- It is async-capable (ASGI), but because the RAG pipeline is CPU- and network-bound (embedding server, LLM server, database), the endpoints in this project use plain synchronous handlers. FastAPI handles them correctly by running them in a thread pool.
- Auto-generated `/docs` (Swagger UI) and `/redoc` pages are available out of the box — useful for manual testing without a frontend.

### Backend runtime: uvicorn

uvicorn is the ASGI server that actually runs the FastAPI application. It listens for HTTP connections and hands them to FastAPI. The application is started with:

```
uvicorn main:app --host 0.0.0.0 --port 8001
```

`main` refers to `api/main.py`, and `app` is the FastAPI instance defined there.

### Backend database driver: psycopg (v3)

psycopg3 is the modern PostgreSQL adapter for Python. It handles connection management, query parameterisation (preventing SQL injection), and type coercion between Python and PostgreSQL. The backend connects to the same database used by the preprocessing and generation pipelines — there is no separate application database.

### Auth: JWT in an httpOnly cookie

User sessions are managed with JSON Web Tokens (JWT). When a user logs in, the server creates a signed JWT containing the username and an expiry timestamp, then sets it as an httpOnly cookie. httpOnly means JavaScript running in the browser cannot read the cookie — it is sent automatically by the browser on every request but is invisible to client-side code. This prevents XSS attacks from stealing the session token.

The JWT is signed with a secret key (`JWT_SECRET` in `.env`). If the secret is not set, the server generates a random one at startup — which means all sessions are invalidated on server restart. For persistent sessions, `JWT_SECRET` must be set in `.env`.

### Auth: bcrypt

Passwords are never stored in plaintext. When a user's password is set (via `seed_password.py`), it is hashed with bcrypt. bcrypt is a deliberately slow hashing algorithm designed to resist brute-force attacks. On login, the submitted password is re-hashed and compared to the stored hash using `bcrypt.checkpw`.

### Frontend: Next.js 16 (App Router)

Next.js is a React framework that adds server-side rendering, routing, and build tooling on top of React. This project uses the **App Router** (introduced in Next.js 13), where the file system inside `app/` defines routes directly — a file at `app/chat/page.tsx` becomes the `/chat` route automatically.

Next.js was chosen because:
- The App Router supports both server components (which run on the server and can access cookies, redirect, etc.) and client components (which run in the browser and can use React hooks).
- The built-in `rewrites` feature in `next.config.ts` lets the frontend proxy API calls to the backend without configuring a separate reverse proxy like nginx.
- It handles TypeScript compilation, module bundling, code splitting, and fast refresh out of the box.

### Frontend language: TypeScript

TypeScript is a superset of JavaScript that adds static type checking. All frontend files use `.tsx` (TypeScript with JSX). Type errors are caught at build time rather than at runtime. The `tsconfig.json` configures TypeScript with strict mode enabled.

### Frontend styling: Tailwind CSS v4

Tailwind is a utility-first CSS framework where styling is done by applying small single-purpose class names directly in the HTML/JSX, rather than writing separate CSS files. This project uses Tailwind v4, which has a different configuration model from v3: instead of a `tailwind.config.js` file, configuration is done inside `globals.css` using the `@theme` directive. Tailwind v4 is loaded via PostCSS (configured in `postcss.config.mjs`) and the `@tailwindcss/postcss` plugin.

### Frontend package manager: bun (or npm)

The `package.json` defines the project dependencies. The `README.md` inside `web/` shows `bun dev` as the development command, meaning the team uses bun as the package manager and runner. Bun is a fast JavaScript runtime and package manager that is a drop-in replacement for Node.js + npm for most purposes. `package-lock.json` is also present, meaning npm is also compatible.

---

## Chronological dependency order

The following sections explain each file in the order that things need to exist before they can be used.

---

### 1. `.env` — environment variables (prerequisite for the API)

Before the API can start, a `.env` file must exist at the repo root containing at minimum:

```
DATABASE_URL=postgresql://user:pass@host:port/dbname
JWT_SECRET=some-long-random-string
```

`DATABASE_URL` is the connection string for PostgreSQL. `JWT_SECRET` is the signing key for JWTs. Both are loaded by `deps.py` using `python-dotenv`. Without `DATABASE_URL` the server crashes immediately on the first request that touches the database.

---

### 2. `api/requirements.txt` — Python dependencies

Lists the six packages the API needs:

```
fastapi          — the web framework
uvicorn[standard] — the ASGI server (includes websocket and http/2 support)
python-jose[cryptography] — JWT encoding/decoding
bcrypt           — password hashing
psycopg[binary]  — PostgreSQL driver (binary variant bundles libpq)
python-dotenv    — reads .env into os.environ
```

Install with:
```
pip install -r api/requirements.txt
```

These are installed into the same virtualenv used by the rest of the project.

---

### 3. `api/deps.py` — shared dependencies (the foundation everything else imports)

This is the lowest-level module in the API. It is imported by every other module. It provides two things:

**Database dependency (`get_db`)**

```python
def get_db() -> Generator[psycopg.Connection, None, None]:
```

This is a FastAPI dependency function. FastAPI's dependency injection system calls `get_db()` automatically when a route declares `conn: psycopg.Connection = Depends(get_db)`. It opens a synchronous psycopg3 connection using `DATABASE_URL`, yields it to the route handler, and closes it when the handler returns. Each request gets its own connection.

**Auth dependency (`verify_token`)**

```python
def verify_token(request: Request) -> str:
```

Also a FastAPI dependency. It reads the `ragrats_token` cookie from the incoming request, decodes the JWT, and returns the username (the `sub` claim). If the cookie is missing, expired, or tampered with, it raises a 401 HTTP exception. Routes that declare `username: str = Depends(verify_token)` are automatically protected.

**JWT configuration constants**

`deps.py` also defines `JWT_ALGORITHM = "HS256"`, `JWT_EXPIRE_HOURS = 8`, and `_JWT_SECRET` (loaded from `.env`). These are imported by `auth.py` so there is one source of truth for JWT parameters.

**sys.path bootstrap**

`deps.py` adds the repo root to `sys.path` so that `core/`, `clients/`, and `src/` are importable from anywhere in the API. This is needed because uvicorn starts the process inside `api/`, not the repo root.

---

### 4. `api/seed_password.py` — one-time setup script

Before any user can log in, their password must be stored in the `users` table. This script hashes a plain-text password with bcrypt and writes it to the database.

```
python src/05_application/api/seed_password.py
python src/05_application/api/seed_password.py --username alice --password s3cr3t
```

Defaults: username `developer`, password `developer`. The script upserts — it creates the user if they don't exist, or updates their password if they do. This only needs to be run once per user.

---

### 5. `api/auth.py` — login and logout

Defines the `/auth` router with two endpoints.

**`POST /auth/login`**

Accepts `{"username": "...", "password": "..."}`. It fetches the `password_hash` from the `users` table, runs `bcrypt.checkpw` against the submitted password, and if it matches, creates a JWT with `_create_jwt(username)` and sets it as an httpOnly cookie named `ragrats_token`. The cookie is scoped to `path="/"` so it is sent on every request, and has `samesite="lax"` to prevent cross-site request forgery.

Returns `{"username": "..."}` on success, 401 on failure. The error message is intentionally identical for "wrong username" and "wrong password" — this prevents an attacker from enumerating valid usernames.

**`POST /auth/logout`**

Requires a valid token (uses `verify_token`). Deletes the `ragrats_token` cookie by calling `response.delete_cookie`. The JWT itself is not invalidated server-side (there is no token blocklist), so technically the token remains valid until it expires in 8 hours — but with no cookie, the browser will not send it.

---

### 6. `api/chat.py` — session management and RAG query endpoint

Defines the `/chat` router with two endpoints.

**Configuration constants**

At the top of the file, five constants control the RAG pipeline parameters used by this application layer:

```python
_TOP_K_1 = 500      # candidate pool for voyage key selection
_TOP_K_2 = 20       # final chunk count retrieved
_EXPAND_WINDOW = 2  # neighbour chunks added on each side of an anchor
_TEMPERATURE = 0.3  # LLM sampling temperature
_MAX_TOKENS = 1250  # maximum tokens in the LLM response
```

These can be tuned without touching pipeline code — they are passed directly to `run_query()`.

**`POST /chat/sessions`**

Creates a new query session in the `query_sessions` table. A session groups together all queries made during one browser visit. The endpoint requires authentication (`verify_token`), inserts a row with the authenticated username, and returns the generated `session_id` UUID. The `source` column on `query_sessions` starts as NULL and is filled in by the first query logged to that session.

**`POST /chat/message`**

The main endpoint. Accepts `{"message": "...", "session_id": "..."}`. It:

1. Validates that the `session_id` exists and belongs to the authenticated user (prevents one user from submitting queries under another user's session).
2. Calls `run_query()` from `run_generation.py` with `source="application"` and the `session_id`. This runs the full pipeline: embedding → voyage key selection → chunk retrieval → chunk expansion → context building → LLM generation. It also logs a row to `queries`, `retrieval_logging`, and `generation_logging`, all linked by `query_id`. The `query_sessions.source` is set to `'application'` on the first query.
3. Returns `{"answer": "..."}`.

The endpoint is synchronous (`def`, not `async def`). FastAPI detects this and runs it in a thread pool automatically, so the ASGI event loop is not blocked while the pipeline runs (which can take many seconds).

**sys.path bootstrap**

`chat.py` adds three directories to `sys.path`: repo root (for `core/`, `clients/`), `src/02_retrieval/` (for `step_01_voyage_key`, `step_02_chunk_retrieval`), and `src/03_generation/` (for `run_generation`).

---

### 7. `api/main.py` — application entry point

This is the file uvicorn loads. It creates the FastAPI app, registers middleware, and mounts the routers.

**CORS middleware**

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    ...
)
```

CORS (Cross-Origin Resource Sharing) is a browser security mechanism that blocks JavaScript from calling a different origin than the page was loaded from. During development the frontend runs on `localhost:3000` and the backend on `localhost:8001`. Without this middleware, every API call from the browser would be blocked. The `allow_credentials=True` flag is required so cookies (the JWT) are included in cross-origin requests.

**Routers**

The `auth_router` and `chat_router` are registered here. FastAPI merges their paths — `auth.py` declares `prefix="/auth"` so its routes become `/auth/login` and `/auth/logout`; `chat.py` declares `prefix="/chat"` so its routes become `/chat/sessions` and `/chat/message`.

**`GET /health`**

A minimal endpoint that returns `{"status": "ok"}`. The frontend calls this on page load as a lightweight auth check — if the session cookie is still valid, this returns 200; if not, the frontend redirects to the login page.

---

### 8. `web/package.json` — frontend dependencies

Defines the project name (`web`), version, and NPM scripts:

- `dev` — starts the Next.js development server with hot reload (`next dev`)
- `build` — compiles the TypeScript, bundles assets, and produces an optimised production build (`next build`)
- `start` — serves the production build (`next start`)

Dependencies:
- `next 16.2.4` — the framework
- `react 19.2.4` and `react-dom 19.2.4` — React (the UI library Next.js is built on)

Dev dependencies include TypeScript, type definitions for React and Node, and the Tailwind CSS toolchain.

---

### 9. `web/tsconfig.json` — TypeScript configuration

Key settings:
- `"strict": true` — enables all strict type checks (no implicit `any`, strict null checks, etc.)
- `"jsx": "react-jsx"` — transforms JSX without importing React explicitly in every file
- `"moduleResolution": "bundler"` — uses Next.js/bundler semantics for module resolution rather than classic Node semantics
- `"paths": { "@/*": ["./*"] }` — makes `@/components/Foo` resolve to `web/components/Foo`. This is why all imports in the frontend use `@/` instead of relative paths.
- `"noEmit": true` — TypeScript only type-checks; it does not produce `.js` output files. Next.js handles the actual compilation via its own bundler (Turbopack in dev, Webpack in prod for this version).

---

### 10. `web/postcss.config.mjs` — CSS processing

PostCSS is a CSS transformation tool. It processes `globals.css` and any Tailwind classes found in `.tsx` files. The only plugin configured is `@tailwindcss/postcss`, which is the Tailwind v4 integration. It scans all source files for Tailwind class names and generates the corresponding CSS — only the classes actually used are included in the final CSS bundle.

---

### 11. `web/next.config.ts` — Next.js configuration

The single most important piece of wiring between the frontend and the backend during development:

```typescript
async rewrites() {
  return [
    { source: "/api/:path*", destination: "http://localhost:8001/:path*" },
  ];
}
```

This tells the Next.js dev server: any request that the browser sends to `/api/anything` should be silently forwarded to `http://localhost:8001/anything`. The browser thinks it is talking to its own origin (`localhost:3000`), so there are no CORS issues from the browser's perspective. The request arrives at the FastAPI server with the original cookies intact. Without this rewrite, the CORS policy would block all API calls (or the browser would prompt for credentials).

In production, this rewrite would be replaced by an nginx or reverse proxy configuration that routes `/api/` to the API server and everything else to the Next.js server.

---

### 12. `web/app/globals.css` — global styles

The root CSS file. It does two things:

```css
@import "tailwindcss";
```
This pulls in Tailwind v4's base styles, component layer, and utility classes. All Tailwind utilities become available throughout the app.

```css
@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --font-sans: var(--font-geist-sans);
  --font-mono: var(--font-geist-mono);
}
```
This registers custom CSS variables as Tailwind design tokens. The `--font-geist-sans` and `--font-geist-mono` variables come from the Google Fonts import in `layout.tsx` and become available as `font-sans` and `font-mono` Tailwind classes throughout the app.

---

### 13. `web/app/layout.tsx` — root layout (wraps every page)

In the Next.js App Router, `layout.tsx` at the root of `app/` wraps every route in the application. This one does three things:

1. **Imports Geist fonts** — Geist Sans (a clean sans-serif typeface) and Geist Mono (a monospace variant), both from the `next/font/google` package. Next.js handles font loading optimally: it downloads and self-hosts the fonts, inlines the font-face declarations, and prevents layout shift. The fonts are exposed as CSS variables (`--font-geist-sans`, `--font-geist-mono`) which `globals.css` picks up via the `@theme` block.

2. **Sets page metadata** — the `<title>` and `<meta description>` tags are defined here using Next.js's `Metadata` API. They apply to all pages unless a page overrides them.

3. **Renders the HTML shell** — the `<html>` and `<body>` tags live here, with the font variables applied as CSS classes. Every page's content is inserted where `{children}` appears.

`layout.tsx` is a **server component** (no `"use client"` directive). It runs on the server during both build time and request time. This means it can use Node.js APIs and runs before any JavaScript reaches the browser.

---

### 14. `web/app/page.tsx` — root redirect

The file at `app/page.tsx` handles the `/` route. It is a server component that reads the `ragrats_token` cookie from the request using `cookies()` from `next/headers`. If the cookie exists, it redirects to `/chat`; if not, to `/login`. The user never sees a blank root page — they are always sent somewhere appropriate.

This is only possible as a server component: cookie access and server-side redirects are not available in client components.

---

### 15. `web/lib/api.ts` — API client (browser-side fetch wrappers)

This module is the only place in the frontend that knows about the backend's URL structure. All other components call these functions rather than using `fetch` directly. It exports four functions:

**`handleResponse(res)`** (internal helper)

Checks `res.ok`. If false, it attempts to parse the JSON body and extract the FastAPI `detail` field (the standard FastAPI error format), then throws an `Error` with that message. This means every failed API call surfaces a human-readable error message rather than just "HTTP 401".

**`login(username, password)`**

`POST /api/auth/login` with the credentials as JSON. On success, the server sets the `ragrats_token` cookie — no further action is needed client-side. Returns `{ username }`.

**`logout()`**

`POST /api/auth/logout`. The server clears the cookie. No return value is used.

**`createSession()`**

`POST /api/chat/sessions`. Creates a new session row in the database and returns the `session_id` UUID string. This is called once when the chat page loads, before the user has typed anything.

**`sendMessage(message, sessionId)`**

`POST /api/chat/message` with `{ message, session_id }`. Waits for the full response (this is a regular JSON request, not streaming). Returns the `answer` string from `{ answer: "..." }`. The browser will appear to hang while the pipeline runs — the `LoadingBubble` component in the chat page communicates to the user that the request is in progress.

All four functions include `credentials: "include"` in their fetch options, which instructs the browser to attach cookies even though the request goes to what looks like the same origin (via the Next.js rewrite proxy).

---

### 16. `web/components/ChatBubble.tsx` — message display component

A client component (`"use client"`) that renders a single chat message. It takes two props: `role` (`"user"` or `"assistant"`) and `content` (the message text).

- User messages are aligned to the right, with a white background and black border.
- Assistant messages are aligned to the left, with a black background and white text.

Both use `whitespace-pre-wrap` so that newlines in the assistant's answer are preserved visually. `break-words` ensures long URLs or strings do not overflow their container. Messages are capped at 75% of the container width.

---

### 17. `web/components/LoadingBubble.tsx` — animated waiting indicator

A client component that displays an animated ellipsis (`"."`, `".."`, `"..."`) while the backend is processing a query. It uses `useState` to track how many dots to show (1, 2, or 3) and `useEffect` to set up an interval timer that advances the count every 400ms. The interval is cleared in the cleanup function returned from `useEffect`, so no memory leak occurs when the component is unmounted (i.e., when the answer arrives and `LoadingBubble` is replaced with a `ChatBubble`).

The bubble is styled identically to an assistant `ChatBubble` (black background, white text, left-aligned) so it looks like the assistant is typing.

---

### 18. `web/components/MessageInput.tsx` — text input component

A client component that renders the text input area at the bottom of the chat page. It has two props: `onSend` (a callback that receives the trimmed message text) and `disabled` (boolean, true while waiting for a response).

Key behaviours:
- **Auto-resize**: The `<textarea>` grows vertically as the user types. On every `onChange`, the height is first reset to `"auto"` (so it can shrink) then set to `scrollHeight` (its actual content height). This gives a single-line input that expands to multi-line as needed.
- **Enter to send**: `handleKeyDown` intercepts Enter without Shift and calls `handleSend`, preventing the default newline insertion. Shift+Enter inserts a newline as normal.
- **Send button**: Clicking "Send" calls the same `handleSend` function. The button is disabled when the input is empty or when `disabled` is true.
- **Reset after send**: After `onSend` is called, the value is cleared and the textarea height is reset to `"auto"`.

---

### 19. `web/app/login/page.tsx` — login page

Route: `/login`. A client component (`"use client"`) because it needs React state for the form fields and event handlers for form submission.

The page renders a centred card with the RagRats title, a username field, a password field, an error message area, and a submit button.

`handleSubmit` is called when the form is submitted. It calls `login(username, password)` from `lib/api.ts`. If successful, `router.push("/chat")` navigates to the chat page — the server has already set the cookie, so the chat page will load correctly. If it fails, the error message from the API (e.g. `"Invalid username or password"`) is shown below the form.

The submit button shows `"Signing in…"` while loading and is disabled to prevent double-submission.

---

### 20. `web/app/chat/page.tsx` — the main chat interface

Route: `/chat`. This is the heart of the frontend. It is a client component (`"use client"`) because it manages multiple pieces of React state and handles user interaction.

**State**

- `messages`: array of `{ id, role, content }` objects — the full conversation history displayed in the UI. `id` is a client-generated UUID used as the React list key.
- `sessionId`: the session UUID returned by `createSession()`. Null until the session is established.
- `loading`: boolean, true while a query is in flight.
- `authChecked`: boolean, true once the auth check and session creation have completed. Used to prevent showing the chat UI before it is ready (avoids a flash of an empty or broken state).

**Initialisation (`useEffect` on mount)**

On mount, the page:
1. Fetches `/api/health` to verify the session cookie is still valid. If it gets a 401, it redirects to `/login` immediately.
2. Calls `createSession()` to create a new session in the database.
3. Sets `authChecked = true` to reveal the chat UI.

If `createSession()` throws (e.g. the cookie expired between the health check and the session creation), it catches the error and redirects to `/login`.

**Scroll behaviour (`useEffect` on messages/loading)**

Whenever `messages` or `loading` changes, the scroll container is scrolled to the bottom. This keeps the latest message in view as the conversation grows.

**`handleSend` (wrapped in `useCallback`)**

Called when the user submits a message. The `useCallback` dependency array is `[sessionId, loading]` — the function is re-created only when these change.

Steps:
1. Guard: return early if `sessionId` is null or `loading` is true.
2. Push the user's message into the `messages` array immediately (optimistic update — the user sees their message before the response arrives).
3. Set `loading = true`. This causes `LoadingBubble` to appear and the input to be disabled.
4. Call `await sendMessage(text, sessionId)`. This blocks until the backend returns the full answer (the pipeline typically takes several seconds).
5. On success: push the assistant's answer into `messages`.
6. On error: push an error message (e.g. `"Error: Session not found"`) as an assistant message so the user sees what went wrong.
7. `finally`: set `loading = false` regardless of success or failure.

**Render**

The component renders:
- A fixed header with the "RagRats" title and a "Log out" button.
- A scrollable message list. When the list is empty and not loading, a placeholder `"Ask anything about the project…"` is shown. Each message is a `ChatBubble`. When `loading` is true, a `LoadingBubble` is appended at the bottom.
- A `MessageInput` at the bottom, disabled while loading or before the session is ready.

**`handleLogout`**

Calls `logout()` then redirects to `/login`. The server deletes the cookie on its end; the redirect ensures the browser stops rendering the protected page.

---

## Request flow: end to end

Here is what happens when a user types a question and presses Enter:

1. **`MessageInput.handleKeyDown`** intercepts Enter, calls `onSend(text)`.
2. **`ChatPage.handleSend`** pushes the user message, sets `loading = true`, calls `sendMessage(text, sessionId)`.
3. **`lib/api.ts sendMessage`** fires `POST /api/chat/message` with the message and session ID. The browser attaches the `ragrats_token` cookie automatically.
4. **Next.js rewrite** (`next.config.ts`) forwards the request from `localhost:3000/api/chat/message` to `localhost:8001/chat/message`.
5. **FastAPI** receives the request. The `verify_token` dependency reads the cookie, decodes the JWT, and extracts the username. The `get_db` dependency opens a database connection.
6. **`chat.py send_message`** validates that the `session_id` belongs to the authenticated user.
7. **`run_query()`** (in `run_generation.py`) runs the full pipeline:
   - Embeds the query text via the embedding server.
   - Finds the winning voyage key(s) from the chunks table.
   - Retrieves the top chunks by vector similarity.
   - Expands each chunk with its neighbours for more context.
   - Logs the query to the `queries` table (and updates `query_sessions.source`).
   - Logs the retrieval to `retrieval_logging`.
   - Builds a formatted context string from the chunks.
   - Sends the context + question to the LLM server and waits for the full answer.
   - Logs the generation to `generation_logging` (with real token counts).
   - Returns the answer string.
8. **FastAPI** returns `{"answer": "..."}` as JSON.
9. **`sendMessage`** resolves with the answer string.
10. **`ChatPage.handleSend`** pushes the assistant message, sets `loading = false`.
11. The `LoadingBubble` disappears and the answer appears as a `ChatBubble`.

---

## Starting the application

**Backend:**
```
cd <repo_root>
uvicorn src.05_application.api.main:app --host 0.0.0.0 --port 8001
# or from inside api/:
uvicorn main:app --host 0.0.0.0 --port 8001
```

**Frontend (development):**
```
cd src/05_application/web
bun dev        # or: npm run dev
```

Open `http://localhost:3000`. The root page checks the cookie and redirects to `/login` or `/chat`.

**First-time setup:**
```
python src/05_application/api/seed_password.py --username developer --password yourpassword
```
