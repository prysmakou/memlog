# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About This Repo

User-facing documentation lives in the [GitHub Wiki](https://github.com/prysmakou/memlog/wiki) (installation, configuration, auth, search, MCP setup, reverse proxy). Keep the wiki up to date when changing user-visible behaviour.

Memlog is a self-hosted, database-less note-taking app. Notes are plain `.md` files on disk. The backend is written in Python (FastAPI + Whoosh), the frontend is Vue 3. The Docker image ships both a web UI and an MCP server for AI agents.

## Commands

### Frontend (`/client`)

```bash
npm run dev       # Dev server on port 8080 (proxies API to localhost:8000)
npm run build     # Production build (outputs to client/dist/)
npm run watch     # Watch mode build
```

Formatting: `npx prettier --write .`

### Backend (`/server`)

```bash
just backend      # Python backend on :8000 (auth disabled, notes in ./tmp-notes)
just test         # pytest (50 tests)
just mcp          # MCP server on :8090 (proxies to :8000)
just test-mcp     # MCP server tests (13 tests)
```

### Docker

```bash
just build        # build Docker image (tag=local)
just run          # run Docker image locally (auth disabled)
```

## Architecture

```
client/        Vue 3 SPA (Vite)
server/        Python backend (FastAPI, Whoosh, python-jose)
mcp-server/    Python MCP server (FastMCP, httpx)
```

In development, the Vite dev server (port 8080) proxies `/api/`, `/attachments/`, and `/health` to the Python backend (port 8000). In production (Docker), `uvicorn memlog.main:app` serves both the API and the static frontend on port 8080; `uvicorn memlog_mcp.main:app` runs on port 8090.

### Backend (`server/memlog/`)

- `main.py` — FastAPI app factory (`create_app`), all routes, SPA shell
- `config.py` — `AppConfig` from `MEMLOG_*` env vars, `AuthType` enum
- `models.py` — Pydantic v2 models with camelCase aliases
- `errors.py` — HTTP exceptions, `validate_filename()`
- `auth.py` — JWT HS256, TOTP, `Authenticator` FastAPI dependency
- `notes.py` — `NoteStore`: async CRUD with aiofiles
- `search.py` — `SearchIndex`: Whoosh full-text search, tag extraction, index sync
- `attachments.py` — `AttachmentStore`: multipart upload, collision handling

Notes are plain `.md` files in `MEMLOG_PATH`. Full-text search index is in `MEMLOG_PATH/.memlog/`. There is no database.

### MCP Server (`mcp-server/memlog_mcp/`)

- `main.py` — FastMCP app, 8 tools, httpx client proxying to the backend API

### Frontend (`client/`)

- `src/main.js` — App entry, Pinia + Vue Router setup
- `src/App.vue` — Root layout: navbar, search modal, global keyboard shortcuts
- `src/views/` — Route-level components (Home, LogIn, Note editor, SearchResults)
- `src/components/` — Reusable UI components including the TOAST UI markdown editor wrapper
- `src/api.js` — Axios instance with JWT auth interceptor
- `src/globalStore.js` — Pinia store for shared state
- `src/tokenStorage.js` — JWT token persistence in localStorage
- `src/router.js` — Vue Router routes

Theming uses CSS custom properties defined in Tailwind config (`tailwind.config.js`) for runtime color switching.
