# Reverse Proxy

Memlog can be served behind a reverse proxy. If you expose it at a sub-path (e.g. `https://example.com/notes`), set `MEMLOG_PATH_PREFIX` so the frontend assets and API routes are correctly prefixed.

## nginx

### Root path (`https://notes.example.com`)

```nginx
server {
    listen 443 ssl;
    server_name notes.example.com;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Sub-path (`https://example.com/notes`)

```nginx
location /notes {
    proxy_pass http://localhost:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

Add to your compose environment:

```yaml
MEMLOG_PATH_PREFIX: /notes
```

## Caddy

### Root path

```
notes.example.com {
    reverse_proxy localhost:8080
}
```

### Sub-path

```
example.com {
    handle_path /notes* {
        reverse_proxy localhost:8080
    }
}
```

Add to your compose environment:

```yaml
MEMLOG_PATH_PREFIX: /notes
```

## MCP server behind a proxy

The MCP server runs on port `8090`. To expose it through the proxy:

```nginx
location /mcp-proxy/ {
    proxy_pass http://localhost:8090/;
}
```

Or expose port `8090` directly and connect AI agents to `http://<host>:8090/mcp`.

## Notes

- `MEMLOG_PATH_PREFIX` must start with `/` and not end with `/` (e.g. `/notes`, not `/notes/`).
- The prefix is patched into the frontend `index.html` at startup, so changing it requires a container restart.
