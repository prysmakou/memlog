from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memlog.config import AuthType
from memlog.notes import NoteStore

from .conftest import make_config

# ── NoteStore unit tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_get(tmp_path: Path) -> None:
    store = NoteStore(tmp_path, tmp_path / ".idx")
    note = await store.create("hello", "world")
    assert note.title == "hello"
    assert note.content == "world"

    fetched = await store.get("hello")
    assert fetched.content == "world"


@pytest.mark.asyncio
async def test_create_strips_whitespace(tmp_path: Path) -> None:
    store = NoteStore(tmp_path, tmp_path / ".idx")
    note = await store.create("  spaced  ", "content")
    assert note.title == "spaced"


@pytest.mark.asyncio
async def test_create_conflict(tmp_path: Path) -> None:
    store = NoteStore(tmp_path, tmp_path / ".idx")
    await store.create("dup", "a")
    with pytest.raises(Exception) as exc:
        await store.create("dup", "b")
    assert exc.value.status_code == 409  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_not_found(tmp_path: Path) -> None:
    store = NoteStore(tmp_path, tmp_path / ".idx")
    with pytest.raises(Exception) as exc:
        await store.get("missing")
    assert exc.value.status_code == 404  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_update_content(tmp_path: Path) -> None:
    store = NoteStore(tmp_path, tmp_path / ".idx")
    await store.create("note", "old")
    updated = await store.update("note", None, "new")
    assert updated.content == "new"


@pytest.mark.asyncio
async def test_update_title(tmp_path: Path) -> None:
    store = NoteStore(tmp_path, tmp_path / ".idx")
    await store.create("old-title", "content")
    updated = await store.update("old-title", "new-title", None)
    assert updated.title == "new-title"
    assert not (tmp_path / "old-title.md").exists()
    assert (tmp_path / "new-title.md").exists()


@pytest.mark.asyncio
async def test_update_title_conflict(tmp_path: Path) -> None:
    store = NoteStore(tmp_path, tmp_path / ".idx")
    await store.create("a", "")
    await store.create("b", "")
    with pytest.raises(Exception) as exc:
        await store.update("a", "b", None)
    assert exc.value.status_code == 409  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_update_not_found(tmp_path: Path) -> None:
    store = NoteStore(tmp_path, tmp_path / ".idx")
    with pytest.raises(Exception) as exc:
        await store.update("ghost", None, "x")
    assert exc.value.status_code == 404  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_delete(tmp_path: Path) -> None:
    store = NoteStore(tmp_path, tmp_path / ".idx")
    await store.create("bye", "")
    await store.delete("bye")
    assert not (tmp_path / "bye.md").exists()


@pytest.mark.asyncio
async def test_delete_not_found(tmp_path: Path) -> None:
    store = NoteStore(tmp_path, tmp_path / ".idx")
    with pytest.raises(Exception) as exc:
        await store.delete("ghost")
    assert exc.value.status_code == 404  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_invalid_title(tmp_path: Path) -> None:
    store = NoteStore(tmp_path, tmp_path / ".idx")
    with pytest.raises(Exception) as exc:
        await store.create("bad/title", "")
    assert exc.value.status_code == 400  # type: ignore[attr-defined]


# ── Route tests ───────────────────────────────────────────────────────────────


def test_route_create_get_delete(client: TestClient) -> None:
    r = client.post("/api/notes", json={"title": "test", "content": "hello"})
    assert r.status_code == 201
    assert r.json()["title"] == "test"

    r = client.get("/api/notes/test")
    assert r.status_code == 200
    assert r.json()["content"] == "hello"

    r = client.delete("/api/notes/test")
    assert r.status_code == 204


def test_route_update(client: TestClient) -> None:
    client.post("/api/notes", json={"title": "upd", "content": "v1"})
    r = client.patch("/api/notes/upd", json={"newContent": "v2"})
    assert r.status_code == 200
    assert r.json()["content"] == "v2"


def test_route_read_only_blocks_write(tmp_path: Path) -> None:
    from memlog.main import create_app

    cfg = make_config(tmp_path, auth_type=AuthType.READ_ONLY)
    c = TestClient(create_app(cfg))
    r = c.post("/api/notes", json={"title": "x", "content": ""})
    assert r.status_code == 404  # route not registered
