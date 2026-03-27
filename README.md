[![Build](https://github.com/prysmakou/memlog/actions/workflows/build.yml/badge.svg)](https://github.com/prysmakou/memlog/actions/workflows/build.yml)
[![Docker](https://ghcr-badge.egpl.dev/prysmakou/memlog/latest_tag?trim=major&label=docker)](https://github.com/prysmakou/memlog/pkgs/container/memlog)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Markdown notes for humans, MCP-native for AI agents.

A self-hosted, database-less note-taking app. Notes are plain `.md` files on disk. The backend is written in Python (FastAPI + Whoosh), the frontend is Vue 3. The Docker image ships both a web UI and an MCP server for AI agents.

> Inspired by [flatnotes](https://github.com/dullage/flatnotes) by dullage.

## Quick start

```yaml
services:
  memlog:
    image: ghcr.io/prysmakou/memlog:latest
    ports:
      - "8080:8080" # web UI + API
      - "8090:8090" # MCP server
    volumes:
      - ./notes:/data
    environment:
      MEMLOG_PATH: /data
      MEMLOG_AUTH_TYPE: password
      MEMLOG_USERNAME: admin
      MEMLOG_PASSWORD: changeme
      MEMLOG_SECRET_KEY: change-this-to-a-random-secret
    restart: unless-stopped
```

```bash
docker compose up -d
```

Open `http://localhost:8080`. Full docs at **[prysmakou.github.io/memlog](https://prysmakou.github.io/memlog/)**.

## MCP Server

Memlog ships a built-in MCP server ([Streamable HTTP](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#streamable-http)) on port `8090`.

**Tools:** `list_notes`, `search_notes`, `get_note`, `create_note`, `append_to_note`, `update_note`, `delete_note`, `list_tags`

```bash
claude mcp add --transport http --scope user memlog http://<host>:8090/mcp
```

See the [MCP Server docs](https://prysmakou.github.io/memlog/mcp-server/) for auth token setup.

## Development

Install [just](https://just.systems/man/en/packages.html), [uv](https://docs.astral.sh/uv/), and Node 22, then:

```bash
just install      # npm deps + git hooks
just backend      # Python backend on :8000 (auth disabled, notes in ./tmp-notes)
just frontend     # Vue dev server on :8080 (proxies API to :8000)
just test         # pytest (50 tests)
just test-mcp     # MCP server tests (13 tests)
just build        # build Docker image (tag=local)
just run          # run Docker image locally (auth disabled)
```

## Architecture

```
client/       Vue 3 SPA (Vite)
server/       Python backend (FastAPI, Whoosh)
mcp-server/   Python MCP server (FastMCP, Streamable HTTP)
```

Notes are stored as plain `.md` files in `MEMLOG_PATH`. Full-text search uses a [Whoosh](https://whoosh.readthedocs.io/) index stored in `MEMLOG_PATH/.memlog/`. There is no database.

**Optional:** semantic (vector) search via [Qdrant](https://qdrant.tech/) + [Voyage AI](https://www.voyageai.com/) or [Ollama](https://ollama.com/). Set `MEMLOG_QDRANT_URL` to enable; see the [Search docs](https://prysmakou.github.io/memlog/search/#semantic-search) for setup.
