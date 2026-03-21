"""Unit tests for the MCP server tools.

Uses respx to mock httpx calls — no running server required.
The MEMLOG_TOKEN env var is set so _authed_client skips the login step.
"""

import os

import respx
from httpx import Response

os.environ.setdefault("MEMLOG_TOKEN", "test-token")
os.environ.setdefault("MEMLOG_URL", "http://memlog.test")

import mcp_server  # noqa: E402  (must come after env setup)

BASE = "http://memlog.test"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def note(title, content="body", last_modified=1000.0):
    return {"title": title, "content": content, "lastModified": last_modified}


def search_result(title, last_modified=1000.0):
    return {
        "title": title,
        "lastModified": last_modified,
        "score": None,
        "titleHighlights": None,
        "contentHighlights": None,
        "tagMatches": None,
    }


# ---------------------------------------------------------------------------
# list_notes
# ---------------------------------------------------------------------------


@respx.mock
def test_list_notes_returns_title_and_last_modified():
    respx.get(f"{BASE}/api/search").mock(
        return_value=Response(
            200,
            json=[
                search_result("Alpha", 2000.0),
                search_result("Beta", 1000.0),
            ],
        )
    )
    result = mcp_server.list_notes()
    assert result == [
        {"title": "Alpha", "lastModified": 2000.0},
        {"title": "Beta", "lastModified": 1000.0},
    ]


@respx.mock
def test_list_notes_strips_content_fields():
    respx.get(f"{BASE}/api/search").mock(
        return_value=Response(200, json=[search_result("Note")])
    )
    result = mcp_server.list_notes()
    assert "content" not in result[0]
    assert "score" not in result[0]


# ---------------------------------------------------------------------------
# search_notes
# ---------------------------------------------------------------------------


@respx.mock
def test_search_notes_passes_term():
    route = respx.get(f"{BASE}/api/search").mock(
        return_value=Response(200, json=[search_result("Match")])
    )
    mcp_server.search_notes(term="hello")
    assert route.called
    assert route.calls[0].request.url.params["term"] == "hello"


@respx.mock
def test_search_notes_passes_limit():
    route = respx.get(f"{BASE}/api/search").mock(
        return_value=Response(200, json=[])
    )
    mcp_server.search_notes(term="*", limit=5)
    assert route.calls[0].request.url.params["limit"] == "5"


# ---------------------------------------------------------------------------
# get_note
# ---------------------------------------------------------------------------


@respx.mock
def test_get_note_returns_note():
    respx.get(f"{BASE}/api/notes/My Note").mock(
        return_value=Response(200, json=note("My Note", "hello"))
    )
    result = mcp_server.get_note("My Note")
    assert result["title"] == "My Note"
    assert result["content"] == "hello"


# ---------------------------------------------------------------------------
# create_note
# ---------------------------------------------------------------------------


@respx.mock
def test_create_note_posts_title_and_content():
    route = respx.post(f"{BASE}/api/notes").mock(
        return_value=Response(200, json=note("New", "content"))
    )
    mcp_server.create_note("New", "content")
    body = route.calls[0].request.read()
    assert b'"New"' in body
    assert b'"content"' in body


# ---------------------------------------------------------------------------
# append_to_note
# ---------------------------------------------------------------------------


@respx.mock
def test_append_adds_content_after_existing():
    respx.get(f"{BASE}/api/notes/Log").mock(
        return_value=Response(200, json=note("Log", "existing"))
    )
    patch_route = respx.patch(f"{BASE}/api/notes/Log").mock(
        return_value=Response(200, json=note("Log", "existing\n\nnew entry"))
    )
    mcp_server.append_to_note("Log", "new entry")
    sent = patch_route.calls[0].request.read()
    assert b"existing" in sent
    assert b"new entry" in sent


@respx.mock
def test_append_separator_when_content_ends_with_newline():
    respx.get(f"{BASE}/api/notes/Log").mock(
        return_value=Response(200, json=note("Log", "existing\n"))
    )
    patch_route = respx.patch(f"{BASE}/api/notes/Log").mock(
        return_value=Response(200, json=note("Log", "existing\nnew"))
    )
    mcp_server.append_to_note("Log", "new")
    sent = patch_route.calls[0].request.read().decode()
    # existing ends with \n: separator \n → blank line before new content
    assert "existing\\n\\nnew" in sent


@respx.mock
def test_append_separator_when_content_missing_trailing_newline():
    respx.get(f"{BASE}/api/notes/Log").mock(
        return_value=Response(200, json=note("Log", "existing"))
    )
    patch_route = respx.patch(f"{BASE}/api/notes/Log").mock(
        return_value=Response(200, json=note("Log", "existing\n\nnew"))
    )
    mcp_server.append_to_note("Log", "new")
    sent = patch_route.calls[0].request.read().decode()
    # double newline separator when content has no trailing newline
    assert "existing\\n\\nnew" in sent


# ---------------------------------------------------------------------------
# update_note
# ---------------------------------------------------------------------------


@respx.mock
def test_update_note_content():
    route = respx.patch(f"{BASE}/api/notes/Old").mock(
        return_value=Response(200, json=note("Old", "new body"))
    )
    mcp_server.update_note("Old", new_content="new body")
    sent = route.calls[0].request.read()
    assert b"newContent" in sent
    assert b"newTitle" not in sent


@respx.mock
def test_update_note_title():
    route = respx.patch(f"{BASE}/api/notes/Old").mock(
        return_value=Response(200, json=note("New"))
    )
    mcp_server.update_note("Old", new_title="New")
    sent = route.calls[0].request.read()
    assert b"newTitle" in sent
    assert b"newContent" not in sent


# ---------------------------------------------------------------------------
# delete_note
# ---------------------------------------------------------------------------


@respx.mock
def test_delete_note_calls_delete_endpoint():
    route = respx.delete(f"{BASE}/api/notes/Gone").mock(
        return_value=Response(204)
    )
    mcp_server.delete_note("Gone")
    assert route.called


@respx.mock
def test_delete_note_returns_confirmation():
    respx.delete(f"{BASE}/api/notes/Gone").mock(return_value=Response(204))
    result = mcp_server.delete_note("Gone")
    assert "Gone" in result


# ---------------------------------------------------------------------------
# list_tags
# ---------------------------------------------------------------------------


@respx.mock
def test_list_tags_returns_list():
    respx.get(f"{BASE}/api/tags").mock(
        return_value=Response(200, json=["ai", "work"])
    )
    result = mcp_server.list_tags()
    assert result == ["ai", "work"]


# ---------------------------------------------------------------------------
# auth — token from env vs username/password login
# ---------------------------------------------------------------------------


def test_authed_client_uses_token_from_env(monkeypatch):
    monkeypatch.setenv("MEMLOG_TOKEN", "my-token")
    monkeypatch.delenv("MEMLOG_USERNAME", raising=False)
    with mcp_server._authed_client() as client:
        assert client.headers["authorization"] == "Bearer my-token"


@respx.mock
def test_authed_client_logs_in_with_username_password(monkeypatch):
    monkeypatch.delenv("MEMLOG_TOKEN", raising=False)
    monkeypatch.setenv("MEMLOG_USERNAME", "alice")
    monkeypatch.setenv("MEMLOG_PASSWORD", "secret")
    respx.post(f"{BASE}/api/token").mock(
        return_value=Response(200, json={"access_token": "logged-in-token"})
    )
    with mcp_server._authed_client() as client:
        assert client.headers["authorization"] == "Bearer logged-in-token"
