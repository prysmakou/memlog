# Search

## Full-text search

Memlog uses [Whoosh](https://whoosh.readthedocs.io/) for full-text search. The index is stored in `MEMLOG_PATH/.memlog/` and updated automatically before each search — new or modified notes appear immediately.

### Syntax

| Query           | Matches                                                  |
| --------------- | -------------------------------------------------------- |
| `hello world`   | Notes containing both words                              |
| `"hello world"` | Notes containing the exact phrase                        |
| `prog*`         | Prefix wildcard — matches `program`, `programming`, etc. |
| `*`             | All notes                                                |
| `#work`         | Notes tagged `#work`                                     |
| `#work meeting` | Notes tagged `#work` that also contain `meeting`         |

Search applies stemming and ASCII folding, so `program`, `programming`, and `programmed` all match the same query.

### Tags

Tags are `#word` tokens in note content. They are case-insensitive. Use `#tag` as a standalone query to filter by tag, or combine with keywords.

### Sort options

Results can be sorted by:

- **Score** — relevance (default for keyword searches)
- **Last Modified** — most recently changed first
- **Title** — alphabetical

---

## Semantic search

Semantic search finds notes by meaning rather than exact keywords. It uses vector embeddings stored in [Qdrant](https://qdrant.tech/).

Semantic search is **optional** and disabled by default. The **Semantic** toggle in the search UI only appears when it is configured and reachable at startup.

### Requirements

- A running **Qdrant** instance
- An **embedding provider**: Voyage AI (cloud) or Ollama (local)

### Option 1: Voyage AI (recommended)

[Voyage AI](https://www.voyageai.com/) is a managed embeddings API with a free tier (200M tokens/month). No local GPU required.

```yaml
MEMLOG_QDRANT_URL: http://qdrant:6333
MEMLOG_VOYAGE_API_KEY: your-voyage-api-key
MEMLOG_EMBEDDING_MODEL: voyage-3-lite
```

Add Qdrant to your `docker-compose.yml`:

```yaml
services:
  memlog:
    image: ghcr.io/prysmakou/memlog:latest
    environment:
      MEMLOG_PATH: /data
      MEMLOG_QDRANT_URL: http://qdrant:6333
      MEMLOG_VOYAGE_API_KEY: your-voyage-api-key
      MEMLOG_EMBEDDING_MODEL: voyage-3-lite
      # ... other vars

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - ./qdrant:/qdrant/storage
```

Get an API key at [voyageai.com](https://www.voyageai.com/).

### Option 2: Ollama (local)

[Ollama](https://ollama.com/) runs models locally. Heavier on CPU; no API key needed.

```yaml
MEMLOG_QDRANT_URL: http://qdrant:6333
MEMLOG_OLLAMA_URL: http://ollama:11434
MEMLOG_EMBEDDING_MODEL: nomic-embed-text
```

Add both Qdrant and Ollama to your compose file:

```yaml
services:
  memlog:
    image: ghcr.io/prysmakou/memlog:latest
    environment:
      MEMLOG_PATH: /data
      MEMLOG_QDRANT_URL: http://qdrant:6333
      MEMLOG_OLLAMA_URL: http://ollama:11434
      MEMLOG_EMBEDDING_MODEL: nomic-embed-text
      # ... other vars

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - ./qdrant:/qdrant/storage

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ./ollama:/root/.ollama
```

Pull the embedding model before first use:

```bash
docker exec ollama ollama pull nomic-embed-text
```

### Startup checks and fallback

At startup, Memlog checks that both Qdrant and the embedding provider (Voyage AI or Ollama) are reachable. If either check fails, semantic search is **disabled with a log warning** — the app continues to work normally with full-text search only. This means a misconfigured or unreachable dependency does not prevent the app from starting.

```
WARNING  Semantic search disabled: cannot reach Qdrant (...)
```

### Switching embedding models

If you change from one provider to another (e.g., Ollama → Voyage AI), the vector dimensions may differ. Memlog detects this automatically at startup and recreates the Qdrant collection, re-embedding all notes on the next search.

### Index management

Notes are embedded on first search and kept in sync automatically. Each search triggers a sync pass that:

- Embeds new or modified notes (detected by file modification time)
- Removes deleted notes from the index

To force a full re-index, delete the Qdrant collection or recreate the Qdrant volume.
