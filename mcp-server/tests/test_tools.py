import json

import pytest
import respx
from httpx import Response

import memlog_mcp.main as m


BASE = "http://localhost:8080"


@pytest.fixture(autouse=True)
def reset_token():
    """Reset cached token between tests so auth state doesn't bleed across."""
    original = m._cached_token
    m._cached_token = None
    yield
    m._cached_token = original


# ── list_notes ────────────────────────────────────────────────────────────────


@respx.mock
async def test_list_notes_returns_title_and_timestamp() -> None:
    respx.get(f"{BASE}/api/search").mock(
        return_value=Response(
            200,
            json=[
                {"title": "alpha", "lastModified": 1000.0, "score": 1.0},
                {"title": "beta", "lastModified": 2000.0, "score": 0.5},
            ],
        )
    )
    result = await m.list_notes()
    notes = json.loads(result)
    assert notes == [
        {"title": "alpha", "lastModified": 1000.0},
        {"title": "beta", "lastModified": 2000.0},
    ]


@respx.mock
async def test_list_notes_passes_sort_params() -> None:
    route = respx.get(f"{BASE}/api/search").mock(return_value=Response(200, json=[]))
    await m.list_notes(sort="title", order="asc", limit=10)
    assert route.called
    qs = route.calls[0].request.url.params
    assert qs["sort"] == "title"
    assert qs["order"] == "asc"
    assert qs["limit"] == "10"


# ── search_notes ──────────────────────────────────────────────────────────────


@respx.mock
async def test_search_notes_passes_term() -> None:
    payload = [{"title": "rust", "lastModified": 1.0, "score": 0.9}]
    route = respx.get(f"{BASE}/api/search").mock(return_value=Response(200, json=payload))
    result = await m.search_notes(term="rust")
    assert json.loads(result) == payload
    assert route.calls[0].request.url.params["term"] == "rust"


# ── get_note ──────────────────────────────────────────────────────────────────


@respx.mock
async def test_get_note_returns_json() -> None:
    payload = {"title": "rust", "content": "hello", "lastModified": 1.0}
    respx.get(f"{BASE}/api/notes/rust").mock(return_value=Response(200, json=payload))
    result = await m.get_note("rust")
    assert json.loads(result) == payload


# ── create_note ───────────────────────────────────────────────────────────────


@respx.mock
async def test_create_note_posts_and_returns_message() -> None:
    route = respx.post(f"{BASE}/api/notes").mock(
        return_value=Response(201, json={"title": "new", "content": "", "lastModified": 1.0})
    )
    result = await m.create_note("new", "hello")
    assert result == "Created 'new'."
    assert json.loads(route.calls[0].request.content) == {"title": "new", "content": "hello"}


# ── append_to_note ────────────────────────────────────────────────────────────


@respx.mock
async def test_append_to_note_concatenates_content() -> None:
    respx.get(f"{BASE}/api/notes/my-note").mock(
        return_value=Response(200, json={"title": "my-note", "content": "existing", "lastModified": 1.0})
    )
    patch_route = respx.patch(f"{BASE}/api/notes/my-note").mock(
        return_value=Response(200, json={"title": "my-note", "content": "existing\n\nnew", "lastModified": 2.0})
    )
    result = await m.append_to_note("my-note", "new")
    assert result == "Appended to 'my-note'."
    body = json.loads(patch_route.calls[0].request.content)
    assert body["newContent"] == "existing\n\nnew"


@respx.mock
async def test_append_single_newline_when_content_ends_with_newline() -> None:
    respx.get(f"{BASE}/api/notes/note").mock(
        return_value=Response(200, json={"title": "note", "content": "line\n", "lastModified": 1.0})
    )
    patch_route = respx.patch(f"{BASE}/api/notes/note").mock(
        return_value=Response(200, json={"title": "note", "content": "line\nappended", "lastModified": 2.0})
    )
    await m.append_to_note("note", "appended")
    body = json.loads(patch_route.calls[0].request.content)
    # "line\n" + "\n" (separator) + "appended" = "line\n\nappended" (paragraph break)
    assert body["newContent"] == "line\n\nappended"


# ── update_note ───────────────────────────────────────────────────────────────


@respx.mock
async def test_update_note_content() -> None:
    route = respx.patch(f"{BASE}/api/notes/old").mock(
        return_value=Response(200, json={"title": "old", "content": "new content", "lastModified": 2.0})
    )
    result = await m.update_note("old", new_content="new content")
    assert result == "Updated 'old'."
    assert json.loads(route.calls[0].request.content) == {"newContent": "new content"}


@respx.mock
async def test_update_note_rename() -> None:
    route = respx.patch(f"{BASE}/api/notes/old").mock(
        return_value=Response(200, json={"title": "renamed", "content": "", "lastModified": 2.0})
    )
    result = await m.update_note("old", new_title="renamed")
    assert result == "Updated 'renamed'."
    assert json.loads(route.calls[0].request.content) == {"newTitle": "renamed"}


# ── delete_note ───────────────────────────────────────────────────────────────


@respx.mock
async def test_delete_note() -> None:
    route = respx.delete(f"{BASE}/api/notes/gone").mock(return_value=Response(204))
    result = await m.delete_note("gone")
    assert result == "Deleted 'gone'."
    assert route.called


# ── list_tags ─────────────────────────────────────────────────────────────────


@respx.mock
async def test_list_tags() -> None:
    respx.get(f"{BASE}/api/tags").mock(return_value=Response(200, json=["python", "rust"]))
    result = await m.list_tags()
    assert json.loads(result) == ["python", "rust"]


# ── auth: bearer token ────────────────────────────────────────────────────────


@respx.mock
async def test_static_token_sent_as_bearer() -> None:
    m._cached_token = "mytoken"
    route = respx.get(f"{BASE}/api/tags").mock(return_value=Response(200, json=[]))
    await m.list_tags()
    assert route.calls[0].request.headers["authorization"] == "Bearer mytoken"


@respx.mock
async def test_no_auth_header_when_no_token() -> None:
    route = respx.get(f"{BASE}/api/tags").mock(return_value=Response(200, json=[]))
    await m.list_tags()
    assert "authorization" not in route.calls[0].request.headers
