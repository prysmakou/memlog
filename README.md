> **Note:** This is a personal fork of [flatnotes](https://github.com/dullage/flatnotes). The upstream project no longer accepts pull requests — this fork picks up where it left off. PRs are welcome.

A self-hosted, database-less note-taking web app that utilises a flat folder of markdown files for storage.

## Claude Code MCP Server

Memlog ships an [MCP](https://modelcontextprotocol.io) server so Claude Code can read and write your notes directly.

**Tools exposed:** `search_notes`, `get_note`, `create_note`, `update_note`, `delete_note`, `list_tags`

### Setup

1. Install MCP dependencies:

```bash
just install-mcp
```

2. Create `.mcp.json` in the repo root (it's gitignored):

```json
{
  "mcpServers": {
    "memlog": {
      "command": "uv",
      "args": ["run", "--group", "mcp", "python", "mcp_server.py"],
      "env": {
        "MEMLOG_URL": "http://localhost:8080",
        "MEMLOG_USERNAME": "your-username",
        "MEMLOG_PASSWORD": "your-password"
      }
    }
  }
}
```

For `MEMLOG_AUTH_TYPE=none`, omit `MEMLOG_USERNAME` and `MEMLOG_PASSWORD`.
If you have a token already, set `MEMLOG_TOKEN` instead of username/password.

3. Restart Claude Code — the `memlog` server will appear in `/mcp`.

## Development

Install [just](https://just.systems/man/en/packages.html), then:

```bash
just install   # install all deps (uv + npm) and set up git hooks
just backend   # backend dev server on :8000
just frontend  # frontend dev server on :8080
just test      # run backend tests
just fmt       # auto-fix backend formatting
just build     # build Docker image (tag=local)
just run       # run Docker image locally (auth disabled)
```

Run `just` with no arguments to list all available commands.

`just install` sets up [pre-commit](https://pre-commit.com) git hooks that run ruff, prettier, and basic file checks automatically on every commit.

### Tests

Tests cover helpers, note CRUD + search, and auth. They use temporary directories and require no running server.

## Running with Docker Compose

Create a `docker-compose.yml`:

```yaml
services:
  memlog:
    image: ghcr.io/prysmakou/memlog:latest
    ports:
      - "8080:8080"
    volumes:
      - ./notes:/data/notes
    environment:
      MEMLOG_PATH: /data/notes
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

Then start it:

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
