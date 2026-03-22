import re
import threading
import time
from datetime import UTC
from pathlib import Path

from whoosh import index
from whoosh.analysis import CharsetFilter, StemmingAnalyzer
from whoosh.fields import DATETIME, ID, KEYWORD, TEXT, Schema
from whoosh.highlight import ContextFragmenter, HtmlFormatter, WholeFragmenter
from whoosh.qparser import MultifieldParser
from whoosh.query import Every
from whoosh.searching import Hit
from whoosh.support.charset import accent_map
from whoosh.writing import AsyncWriter

from .models import SearchResult

_SCHEMA_VERSION = "2"
_SCHEMA_VERSION_FILE = ".schema_version"
_MAX_RETRIES = 8
_RETRY_DELAY = 0.25

# Matches #tagname outside of backtick code spans
_TAG_RE = re.compile(r"(^|\s)#([a-zA-Z0-9_-]+)")
_CODE_SPAN_RE = re.compile(r"`{1,3}[^`]*`{1,3}")
_HASHTAG_QUERY_RE = re.compile(r"(^|\s)#([a-zA-Z0-9_-]+)")


def _stemming_folding() -> StemmingAnalyzer:
    # CharsetFilter with accent_map normalizes accented chars (e.g. café → cafe)
    return StemmingAnalyzer() | CharsetFilter(accent_map)


def _build_schema() -> Schema:
    return Schema(
        filename=ID(unique=True, stored=True),
        last_modified=DATETIME(stored=True, sortable=True),
        title=TEXT(field_boost=2.0, analyzer=_stemming_folding(), sortable=True, stored=True),
        content=TEXT(analyzer=_stemming_folding(), stored=True),
        tags=KEYWORD(lowercase=True, field_boost=2.0, commas=True),
    )


def _extract_tags(content: str) -> tuple[str, list[str]]:
    """Return (content_without_tags, tags_list). Tags inside code spans are ignored."""
    stripped = _CODE_SPAN_RE.sub("", content)
    tags = [m.group(2).lower() for m in _TAG_RE.finditer(stripped)]
    clean = _TAG_RE.sub("", content).strip()
    return clean, tags


def _preprocess_query(term: str) -> str:
    """Convert #tag syntax to tags:tag for Whoosh."""

    def replace(m: re.Match[str]) -> str:
        return f"{m.group(1)}tags:{m.group(2)}"

    return _HASHTAG_QUERY_RE.sub(replace, term)


class SearchIndex:
    def __init__(self, notes_path: Path, index_path: Path) -> None:
        self._root = notes_path
        self._index_path = index_path
        self._lock = threading.Lock()
        self._ix = self._open_or_create()

    def _open_or_create(self) -> index.FileIndex:
        schema = _build_schema()
        version_file = self._index_path / _SCHEMA_VERSION_FILE

        if self._index_path.exists():
            stored = version_file.read_text().strip() if version_file.exists() else ""
            if stored != _SCHEMA_VERSION:
                # Schema changed — wipe and rebuild for correctness
                import shutil

                shutil.rmtree(self._index_path)

        if not self._index_path.exists():
            self._index_path.mkdir(parents=True)
            version_file.write_text(_SCHEMA_VERSION)
            return index.create_in(str(self._index_path), schema)

        version_file.write_text(_SCHEMA_VERSION)
        return index.open_dir(str(self._index_path))

    def _sync(self) -> None:
        """Diff filesystem against index and update stale/missing/deleted notes."""
        with self._lock:
            with self._ix.searcher() as searcher:
                indexed: dict[str, float] = {}
                for hit in searcher.search(Every(), limit=None):
                    lm = hit["last_modified"]
                    ts = lm.timestamp() if lm else 0.0
                    indexed[hit["filename"]] = ts

            on_disk: set[str] = set()
            writer = AsyncWriter(self._ix)
            try:
                for p in self._root.glob("*.md"):
                    fname = p.name
                    on_disk.add(fname)
                    disk_mtime = p.stat().st_mtime
                    if disk_mtime != indexed.get(fname, -1):
                        content = p.read_text(errors="replace")
                        content_clean, tags = _extract_tags(content)
                        from datetime import datetime

                        dt = datetime.fromtimestamp(disk_mtime, tz=UTC)
                        writer.update_document(
                            filename=fname,
                            last_modified=dt,
                            title=p.stem,
                            content=content_clean,
                            tags=",".join(tags),
                        )

                for fname in set(indexed) - on_disk:
                    writer.delete_by_term("filename", fname)

                writer.commit()
            except Exception:
                writer.cancel()
                raise

    def _sync_with_retry(self) -> None:
        for attempt in range(_MAX_RETRIES):
            try:
                self._sync()
                return
            except index.LockError:
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAY)
        self._sync()  # final attempt, let it raise

    def search(
        self,
        term: str,
        sort: str = "score",
        order: str = "desc",
        limit: int = 1000,
    ) -> list[SearchResult]:
        self._sync_with_retry()

        reverse = order == "desc"
        processed = _preprocess_query(term)

        with self._ix.searcher() as searcher:
            if processed.strip() == "*":
                from whoosh.sorting import FieldFacet

                sort_field = {
                    "lastModified": "last_modified",
                    "title": "title",
                }.get(sort, "last_modified")
                facet = FieldFacet(sort_field, reverse=reverse)
                hits = searcher.search(Every(), sortedby=facet, limit=limit)
                return [_hit_to_result(h) for h in hits]

            parser = MultifieldParser(["title", "content", "tags"], schema=self._ix.schema)
            query = parser.parse(processed)

            sort_field_opt: str | None = {
                "lastModified": "last_modified",
                "title": "title",
            }.get(sort)

            if sort_field_opt:
                sort_field = sort_field_opt
                from whoosh.sorting import FieldFacet

                facet = FieldFacet(sort_field, reverse=reverse)
                hits = searcher.search(query, sortedby=facet, limit=limit)
            else:
                # Relevance scoring is always highest-first; reverse is n/a here
                hits = searcher.search(query, limit=limit)

            fmt = HtmlFormatter(tagname="strong", classname="match")
            hits.formatter = fmt
            hits.fragmenter = ContextFragmenter(surround=50)

            results = []
            for hit in hits:
                # WholeFragmenter for title (show full title with highlights)
                hits.fragmenter = WholeFragmenter()
                title_hl = hit.highlights("title", top=1)
                hits.fragmenter = ContextFragmenter(surround=50)
                content_hl = hit.highlights("content", top=3)
                results.append(_hit_to_result(hit, title_hl or None, content_hl or None))
            return results

    def get_tags(self) -> list[str]:
        self._sync_with_retry()
        with self._ix.searcher() as searcher:
            reader = searcher.reader()
            tags: set[str] = set()
            for term_text in reader.lexicon("tags"):
                t = term_text.decode("utf-8") if isinstance(term_text, bytes) else term_text
                if t:
                    tags.add(t)
            return sorted(tags)


def _hit_to_result(
    hit: Hit,
    title_highlights: str | None = None,
    content_highlights: str | None = None,
) -> SearchResult:
    lm = hit["last_modified"]
    ts = lm.timestamp() if lm else 0.0
    score: float | None = getattr(hit, "score", None)
    return SearchResult(
        title=hit["title"] if "title" in hit else hit["filename"].removesuffix(".md"),
        last_modified=ts,
        score=score,
        title_highlights=title_highlights,
        content_highlights=content_highlights,
    )
