# Memlog

A self-hosted, database-less note-taking app. Notes are plain `.md` files on disk — no database, no migrations, no lock-in.

**Backend:** Python (FastAPI + Whoosh) · **Frontend:** Vue 3 · **MCP server:** built-in

The Docker image ships a web UI, REST API, and MCP server so AI agents can read and write your notes directly.

---

## Documentation

- [Installation](installation.md) — Docker Compose quick start
- [Configuration](configuration.md) — all `MEMLOG_*` environment variables
- [Authentication](authentication.md) — none, read-only, password, TOTP
- [Search](search.md) — full-text search, tags, wildcards, semantic search
- [MCP Server](mcp-server.md) — tools, Claude Code setup
- [Reverse Proxy](reverse-proxy.md) — nginx and Caddy examples, sub-path prefix
