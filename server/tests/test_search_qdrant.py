"""Tests for QdrantSearchIndex using in-process Qdrant (:memory:) and a mocked embed call."""

import time
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("qdrant_client")

from memlog.config import AppConfig, AuthType  # noqa: E402
from memlog.search_qdrant import QdrantSearchIndex  # noqa: E402

FAKE_VEC = [0.1] * 768


def _cfg(tmp_path: Path) -> AppConfig:
    return AppConfig(
        notes_path=tmp_path,
        auth_type=AuthType.NONE,
        username=None,
        password=None,
        secret_key=None,
        session_expiry_days=30,
        totp_key=None,
        path_prefix="",
        quick_access_hide=False,
        quick_access_title="RECENTLY MODIFIED",
        quick_access_term="*",
        quick_access_sort="lastModified",
        quick_access_limit=4,
        qdrant_url="http://localhost:6333",  # overridden by fixture below
    )


@pytest.fixture
async def index(tmp_path: Path) -> QdrantSearchIndex:
    from qdrant_client import AsyncQdrantClient  # type: ignore[import-untyped]

    idx = QdrantSearchIndex(_cfg(tmp_path), _sync_cooldown=0.0)
    idx._client = AsyncQdrantClient(":memory:")
    return idx


def _batch_mock() -> object:
    """Return an async callable that returns one FAKE_VEC per input text."""

    async def _mock(texts: list[str]) -> list[list[float]]:
        return [FAKE_VEC] * len(texts)

    return _mock


async def test_wildcard_returns_all_notes(index: QdrantSearchIndex, tmp_path: Path) -> None:
    (tmp_path / "alpha.md").write_text("first note")
    (tmp_path / "beta.md").write_text("second note")

    with patch.object(index, "_embed_batch", _batch_mock()):
        results = await index.search("*")

    titles = {r.title for r in results}
    assert titles == {"alpha", "beta"}


async def test_semantic_search_returns_matching_notes(
    index: QdrantSearchIndex, tmp_path: Path
) -> None:
    (tmp_path / "note.md").write_text("hello world")

    with patch.object(index, "_embed_batch", _batch_mock()):
        results = await index.search("hello")

    assert len(results) == 1
    assert results[0].title == "note"
    assert results[0].score is not None


async def test_tag_filter_returns_only_tagged_notes(
    index: QdrantSearchIndex, tmp_path: Path
) -> None:
    (tmp_path / "work-note.md").write_text("content #work")
    (tmp_path / "personal.md").write_text("other content")

    with patch.object(index, "_embed_batch", _batch_mock()):
        results = await index.search("#work")

    assert len(results) == 1
    assert results[0].title == "work-note"


async def test_sync_picks_up_new_note(index: QdrantSearchIndex, tmp_path: Path) -> None:
    with patch.object(index, "_embed_batch", _batch_mock()):
        results = await index.search("*")
    assert len(results) == 0

    (tmp_path / "new.md").write_text("new note content")
    with patch.object(index, "_embed_batch", _batch_mock()):
        results = await index.search("*")
    assert len(results) == 1
    assert results[0].title == "new"


async def test_sync_removes_deleted_note(index: QdrantSearchIndex, tmp_path: Path) -> None:
    note = tmp_path / "temp.md"
    note.write_text("will be deleted")

    with patch.object(index, "_embed_batch", _batch_mock()):
        await index.search("*")

    note.unlink()
    with patch.object(index, "_embed_batch", _batch_mock()):
        results = await index.search("*")
    assert len(results) == 0


async def test_sync_re_embeds_updated_note(index: QdrantSearchIndex, tmp_path: Path) -> None:
    note = tmp_path / "evolving.md"
    note.write_text("original #old")

    embedded_texts: list[str] = []

    async def counting_embed_batch(texts: list[str]) -> list[list[float]]:
        embedded_texts.extend(texts)
        return [FAKE_VEC] * len(texts)

    with patch.object(index, "_embed_batch", counting_embed_batch):
        await index.search("*")

    initial_count = len(embedded_texts)

    # Force mtime change — write new content and nudge mtime
    note.write_text("updated #new")
    import os

    future = time.time() + 1
    os.utime(note, (future, future))

    with patch.object(index, "_embed_batch", counting_embed_batch):
        await index.search("*")

    assert len(embedded_texts) > initial_count


async def test_get_tags_returns_all_tags(index: QdrantSearchIndex, tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("content #alpha #beta")
    (tmp_path / "b.md").write_text("content #beta #gamma")

    with patch.object(index, "_embed_batch", _batch_mock()):
        tags = await index.get_tags()

    assert tags == ["alpha", "beta", "gamma"]


async def test_sort_by_title(index: QdrantSearchIndex, tmp_path: Path) -> None:
    (tmp_path / "zebra.md").write_text("z")
    (tmp_path / "apple.md").write_text("a")
    (tmp_path / "mango.md").write_text("m")

    with patch.object(index, "_embed_batch", _batch_mock()):
        results = await index.search("*", sort="title", order="asc")

    assert [r.title for r in results] == ["apple", "mango", "zebra"]
