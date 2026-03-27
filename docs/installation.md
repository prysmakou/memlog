# Installation

Memlog runs as a single Docker container. The image is available on GitHub Container Registry and includes the web UI, API, and MCP server.

## Quick start

Create a `docker-compose.yml`:

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
      MEMLOG_SECRET_KEY: change-this-to-a-long-random-string
    restart: unless-stopped
```

Generate a strong secret key:

```bash
openssl rand -hex 32
```

Start the container:

```bash
docker compose up -d
```

Open **http://localhost:8080** in your browser.

## Pinning a version

Replace `latest` with a specific tag to pin to a release:

```yaml
image: ghcr.io/prysmakou/memlog:0.1.0
```

Available tags are listed on the [GitHub packages page](https://github.com/prysmakou/notes/pkgs/container/notes).

## Data layout

Memlog creates the following structure inside `MEMLOG_PATH`:

```
/data/
  *.md              ← your notes
  attachments/      ← uploaded files
  .memlog/          ← full-text search index (auto-regenerated if deleted)
```

Only the top-level data directory needs to be backed up. The `.memlog/` index is rebuilt automatically from your notes on the next search if it is missing.
