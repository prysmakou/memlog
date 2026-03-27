# Configuration

All configuration is done through environment variables.

## Required

| Variable      | Description                                                            |
| ------------- | ---------------------------------------------------------------------- |
| `MEMLOG_PATH` | Path where notes (`.md` files) are stored. Must exist before starting. |

## Authentication

| Variable                     | Default    | Description                                                                                                 |
| ---------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------- |
| `MEMLOG_AUTH_TYPE`           | `password` | Auth mode: `none`, `read_only`, `password`, or `totp`                                                       |
| `MEMLOG_USERNAME`            | —          | Login username. Required for `password` and `totp` modes.                                                   |
| `MEMLOG_PASSWORD`            | —          | Login password. Required for `password` and `totp` modes.                                                   |
| `MEMLOG_SECRET_KEY`          | —          | Secret used to sign JWT session tokens. Required for `password` and `totp` modes. Use a long random string. |
| `MEMLOG_TOTP_KEY`            | —          | TOTP seed key. Required when `MEMLOG_AUTH_TYPE=totp`.                                                       |
| `MEMLOG_SESSION_EXPIRY_DAYS` | `30`       | How many days a login session lasts before requiring re-authentication.                                     |

See [Authentication](authentication.md) for details on each auth mode.

## Quick access panel

The quick access panel shows a list of notes on the home screen.

| Variable                    | Default             | Description                                                                                 |
| --------------------------- | ------------------- | ------------------------------------------------------------------------------------------- |
| `MEMLOG_QUICK_ACCESS_HIDE`  | `false`             | Set to `true` to hide the panel entirely.                                                   |
| `MEMLOG_QUICK_ACCESS_TITLE` | `RECENTLY MODIFIED` | Heading shown above the panel.                                                              |
| `MEMLOG_QUICK_ACCESS_TERM`  | `*`                 | Search term used to populate the panel. Change to e.g. `#pinned` to show only tagged notes. |
| `MEMLOG_QUICK_ACCESS_SORT`  | `lastModified`      | Sort order: `lastModified`, `title`, or `score`.                                            |
| `MEMLOG_QUICK_ACCESS_LIMIT` | `4`                 | Number of notes shown.                                                                      |

## Semantic search

Semantic (vector) search requires a running Qdrant instance and an embedding provider. See [Search — Semantic Search](search.md#semantic-search) for setup details.

| Variable                   | Default                  | Description                                                                        |
| -------------------------- | ------------------------ | ---------------------------------------------------------------------------------- |
| `MEMLOG_QDRANT_URL`        | —                        | Qdrant instance URL (e.g. `http://qdrant:6333`). Enables semantic search when set. |
| `MEMLOG_QDRANT_COLLECTION` | `memlog`                 | Qdrant collection name.                                                            |
| `MEMLOG_VOYAGE_API_KEY`    | —                        | Voyage AI API key. When set, uses Voyage AI for embeddings instead of Ollama.      |
| `MEMLOG_OLLAMA_URL`        | `http://localhost:11434` | Ollama base URL. Used when `MEMLOG_VOYAGE_API_KEY` is not set.                     |
| `MEMLOG_EMBEDDING_MODEL`   | `nomic-embed-text`       | Embedding model name. Use `voyage-3-lite` (or similar) when using Voyage AI.       |

## Reverse proxy

| Variable             | Default | Description                                                                                                            |
| -------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------- |
| `MEMLOG_PATH_PREFIX` | ``      | URL path prefix when serving behind a reverse proxy sub-path, e.g. `/notes`. Must start with `/` and not end with `/`. |

See [Reverse Proxy](reverse-proxy.md) for examples.
