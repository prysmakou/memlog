# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About This Repo

This is a personal fork of [flatnotes](https://github.com/dullage/flatnotes). Upstream no longer accepts PRs; changes here serve personal needs and may diverge from the original.

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
# Install deps
pipenv install

# Run dev server (port 8000)
pipenv run python -m uvicorn main:app --app-dir server --reload

# Linting/formatting
pipenv run black server/
pipenv run flake8 server/
pipenv run isort server/
```

No automated test suite exists in this project.

### Docker

```bash
docker build -t notes .
```

The production Docker image runs the FastAPI backend (uvicorn on port 8080) and serves the pre-built frontend as static files.

## Architecture

The repo has two independent parts:

- `client/` — Vue 3 SPA built with Vite
- `server/` — FastAPI backend

In development, the Vite dev server (port 8080) proxies `/api/`, `/attachments/`, and `/health` to the FastAPI backend (port 8000). In production (Docker), a single uvicorn process serves both the API and the static frontend on port 8080.

### Backend (`server/`)

- `main.py` — FastAPI app, all route registrations
- `global_config.py` — All configuration via environment variables (`MEMLOG_PATH`, `MEMLOG_AUTH_TYPE`, etc.)
- `notes/file_system/file_system.py` — Note CRUD backed by the filesystem; Whoosh full-text search index stored in `.memlog/` subdirectory of the notes path
- `auth/` — Auth strategies: `none`, `read_only`, `password`, `totp`
- `attachments/file_system/` — File upload/download handling

Notes are plain `.md` files in `MEMLOG_PATH`. There is no database.

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
