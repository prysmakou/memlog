[![Build](https://github.com/prysmakou/memlog/actions/workflows/build.yml/badge.svg)](https://github.com/prysmakou/memlog/actions/workflows/build.yml)
[![Docker](https://ghcr-badge.egpl.dev/prysmakou/memlog/latest_tag?trim=major&label=docker)](https://github.com/prysmakou/memlog/pkgs/container/memlog)
[![Rust](https://img.shields.io/badge/rust-1.75%2B-orange)](https://www.rust-lang.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Markdown notes for humans, MCP-native for AI agents.

A self-hosted, database-less note-taking app. Notes are plain `.md` files on disk. The backend is written in Rust (axum + tantivy), the frontend is Vue 3. The Docker image ships both a web UI and an MCP server for AI agents.

> Inspired by [flatnotes](https://github.com/dullage/flatnotes) by dullage.

## MCP Server

Memlog ships a Rust MCP server using the [Streamable HTTP](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#streamable-http) transport. It starts automatically inside the Docker image and is accessible at `http://<host>:8090/mcp`.

**Tools:** `list_notes`, `search_notes`, `get_note`, `create_note`, `append_to_note`, `update_note`, `delete_note`, `list_tags`

### Setup (Claude Code)

```bash
claude mcp add --transport http --scope user memlog http://<host>:8090/mcp
```

### Running locally

```bash
just backend   # Rust backend on :8000
just mcp-rs    # MCP server on :8090 (proxies to :8000)
just frontend  # Vue dev server on :8080
```

## Running with Docker Compose

```yaml
services:
  memlog:
    image: ghcr.io/prysmakou/memlog:latest
    ports:
      - "8080:8080" # web UI + API
      - "8090:8090" # MCP server (HTTP + SSE)
    volumes:
      - ./notes:/data
    environment:
      MEMLOG_PATH: /data
      MEMLOG_AUTH_TYPE: password
      MEMLOG_USERNAME: admin
      MEMLOG_PASSWORD: changeme
      MEMLOG_SECRET_KEY: change-this-to-a-random-secret
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped
```

```bash
docker compose up -d
```

Open `http://localhost:8080` in your browser.

### Environment Variables

| Variable                     | Required  | Default             | Description                                                                |
| ---------------------------- | --------- | ------------------- | -------------------------------------------------------------------------- |
| `MEMLOG_PATH`                | yes       | —                   | Path inside the container where notes (`.md` files) are stored             |
| `MEMLOG_AUTH_TYPE`           | no        | `password`          | Auth mode: `none`, `read_only`, `password`, or `totp`                      |
| `MEMLOG_USERNAME`            | if auth   | —                   | Login username (required for `password`/`totp` auth)                       |
| `MEMLOG_PASSWORD`            | if auth   | —                   | Login password (required for `password`/`totp` auth)                       |
| `MEMLOG_SECRET_KEY`          | if auth   | —                   | Secret used to sign JWT tokens — use a long random string                  |
| `MEMLOG_TOTP_KEY`            | if `totp` | —                   | TOTP seed key (required when `MEMLOG_AUTH_TYPE=totp`)                      |
| `MEMLOG_SESSION_EXPIRY_DAYS` | no        | `30`                | How long login sessions last                                               |
| `MEMLOG_PATH_PREFIX`         | no        | ``                  | URL path prefix if serving behind a reverse proxy sub-path (e.g. `/notes`) |
| `MEMLOG_QUICK_ACCESS_HIDE`   | no        | `false`             | Hide the quick-access (recently modified) panel                            |
| `MEMLOG_QUICK_ACCESS_TITLE`  | no        | `RECENTLY MODIFIED` | Title shown above the quick-access panel                                   |
| `MEMLOG_QUICK_ACCESS_TERM`   | no        | `*`                 | Search term used to populate the quick-access panel                        |
| `MEMLOG_QUICK_ACCESS_SORT`   | no        | `lastModified`      | Sort order for quick-access: `score`, `title`, or `lastModified`           |
| `MEMLOG_QUICK_ACCESS_LIMIT`  | no        | `4`                 | Number of notes shown in the quick-access panel                            |

### Auth types

- **`none`** — no login required, full read/write access
- **`read_only`** — no login required, read-only access
- **`password`** — username + password login
- **`totp`** — username + password + TOTP code (scan QR printed to container logs on first start)

## Development

Install [just](https://just.systems/man/en/packages.html) and [Rust](https://rustup.rs/), then:

```bash
just install   # npm deps + git hooks
just backend   # Rust backend on :8000 (auth disabled, notes in ./tmp-notes)
just frontend  # Vue dev server on :8080 (proxies API to :8000)
just test      # cargo test
just build     # build Docker image (tag=local)
just run       # run Docker image locally (auth disabled)
```

Run `just` with no arguments to list all available commands.

### Tests

42 unit tests cover auth, note CRUD, full-text search, tag extraction, and search preprocessing. Tests use temporary directories and require no running server.

```bash
cargo test
```

## Architecture

```
client/        Vue 3 SPA (Vite)
server-rs/     Rust backend (axum, tantivy, tokio)
mcp-server-rs/ Rust MCP server (rmcp, Streamable HTTP)
```

Notes are stored as plain `.md` files in `MEMLOG_PATH`. Full-text search uses a [tantivy](https://github.com/quickwit-oss/tantivy) index stored in `MEMLOG_PATH/.memlog/`. There is no database.
