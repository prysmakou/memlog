# MCP Server

Memlog ships a built-in [Model Context Protocol](https://modelcontextprotocol.io/) server. It starts automatically inside the Docker container on port `8090`. AI agents connect to `http://<host>:8090/mcp` and can read and write your notes directly.

## Available tools

| Tool             | Description                                       |
| ---------------- | ------------------------------------------------- |
| `list_notes`     | List all notes, optionally filtered and sorted    |
| `search_notes`   | Full-text search across titles, content, and tags |
| `get_note`       | Read a note by title                              |
| `create_note`    | Create a new note                                 |
| `append_to_note` | Append text to an existing note                   |
| `update_note`    | Replace a note's content (or rename it)           |
| `delete_note`    | Delete a note                                     |
| `list_tags`      | List all tags used across all notes               |

## Setup with Claude Code

**Step 1 — get your token**

Log in to Memlog, open the menu (top right), and click **Copy MCP Token**. This copies your session JWT to the clipboard. Tokens are valid for 30 days by default (configurable via `MEMLOG_SESSION_EXPIRY_DAYS`).

**Step 2 — register the server**

```bash
claude mcp add-json memlog \
  '{"type":"http","url":"http://<host>:8090/mcp","headers":{"Authorization":"Bearer <your-token>"}}' \
  --scope user
```

Replace `<host>` with your server's IP or hostname (e.g. `192.168.1.10`) and `<your-token>` with the token from step 1.

## Docker Compose

```yaml
services:
  memlog:
    image: ghcr.io/prysmakou/memlog:latest
    ports:
      - "8080:8080" # web UI
      - "8090:8090" # MCP server
    volumes:
      - ./notes:/data
    environment:
      MEMLOG_PATH: /data
      MEMLOG_AUTH_TYPE: password
      MEMLOG_USERNAME: admin
      MEMLOG_PASSWORD: changeme
      MEMLOG_SECRET_KEY: change-this-to-a-long-random-string
```

## Usage examples

Once connected, you can ask your AI agent things like:

- "List all my notes tagged #work"
- "Search my notes for anything about project deadlines"
- "Create a note called 'Meeting notes 2026-03-27' with the following content: ..."
- "Append to my daily log: completed PR review"
- "What did I write about the deployment issue last week?"
