# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About This Repo

Memlog is a self-hosted, database-less note-taking app. Notes are plain `.md` files on disk. The backend is written in Rust (axum + tantivy), the frontend is Vue 3. The Docker image ships both a web UI and an MCP server for AI agents.

## Commands

### Frontend (`/client`)

```bash
npm run dev       # Dev server on port 8080 (proxies API to localhost:8000)
npm run build     # Production build (outputs to client/dist/)
npm run watch     # Watch mode build
```

Formatting: `npx prettier --write .`

### Backend (`/server-rs`)

```bash
just backend      # Rust backend on :8000 (auth disabled, notes in ./tmp-notes)
just test         # cargo test (42 tests)
just mcp-rs       # MCP server on :8090 (proxies to :8000)
```

### Docker

```bash
just build        # build Docker image (tag=local)
just run          # run Docker image locally (auth disabled)
```

## Architecture

```
client/        Vue 3 SPA (Vite)
server-rs/     Rust backend (axum, tantivy, tokio)
mcp-server-rs/ Rust MCP server (rmcp, Streamable HTTP)
```

In development, the Vite dev server (port 8080) proxies `/api/`, `/attachments/`, and `/health` to the Rust backend (port 8000). In production (Docker), `memlog-server` serves both the API and the static frontend on port 8080; `memlog-mcp` runs on port 8090.

### Backend (`server-rs/src/`)

- `main.rs` — axum app setup, `AppState`, startup
- `config.rs` — `AppConfig` from env vars, `AuthType` enum
- `error.rs` — `AppError` enum → HTTP responses, `validate_filename()`
- `models.rs` — request/response structs (`#[serde(rename_all = "camelCase")]`)
- `notes/fs.rs` — note CRUD with `tokio::fs`
- `search/mod.rs` — tantivy full-text search, tag extraction, index sync
- `auth/mod.rs` — JWT HS256, TOTP, `AuthenticatedUser` extractor
- `attachments/fs.rs` — multipart upload, `mime_guess` for Content-Type
- `routes/mod.rs` — all 13 routes, SPA shell, `ServeDir` for static files

Notes are plain `.md` files in `MEMLOG_PATH`. Full-text search index is in `MEMLOG_PATH/.memlog/`. There is no database.

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
