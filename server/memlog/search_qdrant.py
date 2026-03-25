import asyncio
import re
import time
import uuid
from typing import Any

import httpx
from qdrant_client import AsyncQdrantClient  # type: ignore[import-untyped]
from qdrant_client.models import (  # type: ignore[import-untyped]
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from .config import AppConfig
from .models import SearchResult

_TAG_RE = re.compile(r"(^|\s)#([a-zA-Z0-9_-]+)")
_CODE_SPAN_RE = re.compile(r"`{1,3}[^`]*`{1,3}")
_TAG_QUERY_RE = re.compile(r"^\s*#([a-zA-Z0-9_-]+)\s*$")


def _extract_tags(content: str) -> list[str]:
    stripped = _CODE_SPAN_RE.sub("", content)
    return [m.group(2).lower() for m in _TAG_RE.finditer(stripped)]


def _note_id(filename: str) -> str:
    """Deterministic, stable Qdrant point ID derived from the note filename."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, filename))


class QdrantSearchIndex:
    def __init__(self, config: AppConfig, _sync_cooldown: float = 10.0) -> None:
        self._root = config.notes_path
        self._ollama_url = config.ollama_url.rstrip("/")
        self._model = config.embedding_model
        self._collection = config.qdrant_collection
        self._client: Any = AsyncQdrantClient(url=config.qdrant_url)
        self._lock = asyncio.Lock()
        self._initialized = False
        self._last_sync = 0.0
        self._sync_cooldown = _sync_cooldown

    async def _embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient() as http:
            r = await http.post(
                f"{self._ollama_url}/api/embeddings",
                json={"model": self._model, "prompt": text},
                timeout=60.0,
            )
            r.raise_for_status()
            return r.json()["embedding"]  # type: ignore[no-any-return]

    async def _ensure_collection(self) -> None:
        if self._initialized:
            return
        collections = await self._client.get_collections()
        names = {c.name for c in collections.collections}
        if self._collection not in names:
            sample_vec = await self._embed("test")
            await self._client.create_collection(
                self._collection,
                vectors_config=VectorParams(size=len(sample_vec), distance=Distance.COSINE),
            )
        self._initialized = True

    async def _sync(self) -> None:
        now = time.monotonic()
        if now - self._last_sync < self._sync_cooldown:
            return
        async with self._lock:
            # Re-check after acquiring lock (another coroutine may have synced while we waited)
            if time.monotonic() - self._last_sync < self._sync_cooldown:
                return

            await self._ensure_collection()

            stored: dict[str, float] = {}
            offset = None
            while True:
                result, offset = await self._client.scroll(
                    self._collection,
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for point in result:
                    fname = (point.payload or {}).get("filename", "")
                    if fname:
                        stored[fname] = float((point.payload or {}).get("last_modified", 0.0))
                if offset is None:
                    break

            on_disk: set[str] = set()
            to_upsert = []

            for p in self._root.glob("*.md"):
                fname = p.name
                on_disk.add(fname)
                disk_mtime = p.stat().st_mtime
                if disk_mtime == stored.get(fname):
                    continue
                content = p.read_text(errors="replace")
                tags = _extract_tags(content)
                vector = await self._embed(f"{p.stem}\n{content}")
                to_upsert.append(
                    PointStruct(
                        id=_note_id(fname),
                        vector=vector,
                        payload={
                            "filename": fname,
                            "title": p.stem,
                            "tags": tags,
                            "last_modified": disk_mtime,
                        },
                    )
                )

            if to_upsert:
                await self._client.upsert(self._collection, points=to_upsert)

            stale = set(stored) - on_disk
            if stale:
                await self._client.delete(
                    self._collection,
                    points_selector=FilterSelector(
                        filter=Filter(
                            must=[FieldCondition(key="filename", match=MatchAny(any=list(stale)))]
                        )
                    ),
                )

            self._last_sync = time.monotonic()

    async def search(
        self,
        term: str,
        sort: str = "score",
        order: str = "desc",
        limit: int = 1000,
    ) -> list[SearchResult]:
        await self._sync()

        if term.strip() == "*":
            return await self._scroll_sorted(None, sort, order, limit)

        tag_match = _TAG_QUERY_RE.match(term)
        if tag_match:
            tag_filter = Filter(
                must=[
                    FieldCondition(key="tags", match=MatchValue(value=tag_match.group(1).lower()))
                ]
            )
            return await self._scroll_sorted(tag_filter, sort, order, limit)

        vector = await self._embed(term)
        response = await self._client.query_points(
            self._collection,
            query=vector,
            limit=min(limit, 1000),
            with_payload=True,
        )
        return [
            SearchResult(
                title=(h.payload or {}).get(
                    "title", (h.payload or {}).get("filename", "").removesuffix(".md")
                ),
                last_modified=float((h.payload or {}).get("last_modified", 0.0)),
                score=h.score,
            )
            for h in response.points
        ]

    async def _scroll_sorted(
        self,
        scroll_filter: Any,
        sort: str,
        order: str,
        limit: int,
    ) -> list[SearchResult]:
        records: list[Any] = []
        offset = None
        while True:
            batch, offset = await self._client.scroll(
                self._collection,
                scroll_filter=scroll_filter,
                limit=min(256, limit),
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            records.extend(batch)
            if offset is None or len(records) >= limit:
                break

        reverse = order == "desc"
        if sort == "title":
            records.sort(key=lambda r: (r.payload or {}).get("title", "").lower(), reverse=reverse)
        else:
            records.sort(
                key=lambda r: float((r.payload or {}).get("last_modified", 0.0)),
                reverse=reverse,
            )

        return [
            SearchResult(
                title=(r.payload or {}).get(
                    "title", (r.payload or {}).get("filename", "").removesuffix(".md")
                ),
                last_modified=float((r.payload or {}).get("last_modified", 0.0)),
                score=None,
            )
            for r in records[:limit]
        ]

    async def get_tags(self) -> list[str]:
        await self._sync()
        tags: set[str] = set()
        offset = None
        while True:
            batch, offset = await self._client.scroll(
                self._collection,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in batch:
                tags.update((point.payload or {}).get("tags", []))
            if offset is None:
                break
        return sorted(tags)
