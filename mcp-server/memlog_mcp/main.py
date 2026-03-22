import asyncio
import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

_BASE_URL = (os.environ.get("MEMLOG_URL") or "http://localhost:8080").rstrip("/")
_STATIC_TOKEN = (os.environ.get("MEMLOG_TOKEN") or "").strip() or None
_USERNAME = (os.environ.get("MEMLOG_USERNAME") or "").strip() or None
_PASSWORD = (os.environ.get("MEMLOG_PASSWORD") or "").strip() or None

_cached_token: str | None = _STATIC_TOKEN
_login_lock = asyncio.Lock()

mcp = FastMCP(
    "Memlog",
    instructions=(
        "Read and write Memlog notes over HTTP. "
        "Tools: list_notes, search_notes, get_note, create_note, "
        "append_to_note, update_note, delete_note, list_tags."
    ),
)


async def _bearer() -> str | None:
    global _cached_token
    if _cached_token:
        return _cached_token
    if not (_USERNAME and _PASSWORD):
        return None
    async with _login_lock:
        # Re-check after acquiring the lock — another coroutine may have already logged in
        if _cached_token:
            return _cached_token
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{_BASE_URL}/api/token",
                json={"username": _USERNAME, "password": _PASSWORD},
            )
            r.raise_for_status()
            _cached_token = r.json()["access_token"]
    return _cached_token


def _headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


async def _get(path: str, params: dict | None = None) -> object:
    token = await _bearer()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{_BASE_URL}{path}", params=params, headers=_headers(token)
        )
        r.raise_for_status()
        return r.json()


async def _post(path: str, body: dict) -> object:
    token = await _bearer()
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_BASE_URL}{path}", json=body, headers=_headers(token)
        )
        r.raise_for_status()
        return r.json()


async def _patch(path: str, body: dict) -> object:
    token = await _bearer()
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{_BASE_URL}{path}", json=body, headers=_headers(token)
        )
        r.raise_for_status()
        return r.json()


async def _delete(path: str) -> None:
    token = await _bearer()
    async with httpx.AsyncClient() as client:
        r = await client.delete(f"{_BASE_URL}{path}", headers=_headers(token))
        r.raise_for_status()


@mcp.tool(description="List all notes with title and lastModified timestamp (no content).")
async def list_notes(
    sort: str = "lastModified",
    order: str = "desc",
    limit: int = 50,
) -> str:
    data = await _get("/api/search", {"term": "*", "sort": sort, "order": order, "limit": limit})
    notes = [{"title": n["title"], "lastModified": n["lastModified"]} for n in data]  # type: ignore[index,union-attr,attr-defined]
    return json.dumps(notes, indent=2)


@mcp.tool(description="Search notes by keyword, phrase, or #tag. Use * for all notes.")
async def search_notes(
    term: str,
    sort: str = "score",
    order: str = "desc",
    limit: int = 20,
) -> str:
    data = await _get("/api/search", {"term": term, "sort": sort, "order": order, "limit": limit})
    return json.dumps(data, indent=2)


@mcp.tool(description="Get the full content of a note by title.")
async def get_note(title: str) -> str:
    data = await _get(f"/api/notes/{title}")
    return json.dumps(data, indent=2)


@mcp.tool(description="Create a new note.")
async def create_note(title: str, content: str = "") -> str:
    await _post("/api/notes", {"title": title, "content": content})
    return f"Created '{title}'."


@mcp.tool(
    description=(
        "Append content to the end of an existing note. "
        "Safer than update_note — existing content is never overwritten."
    )
)
async def append_to_note(title: str, content: str) -> str:
    existing = await _get(f"/api/notes/{title}")
    current: str = existing["content"]  # type: ignore[index]
    separator = "\n" if current.endswith("\n") else "\n\n"
    await _patch(f"/api/notes/{title}", {"newContent": f"{current}{separator}{content}"})
    return f"Appended to '{title}'."


@mcp.tool(description="Update an existing note's content or title.")
async def update_note(
    title: str,
    new_content: str | None = None,
    new_title: str | None = None,
) -> str:
    body: dict[str, str] = {}
    if new_content is not None:
        body["newContent"] = new_content
    if new_title is not None:
        body["newTitle"] = new_title
    await _patch(f"/api/notes/{title}", body)
    return f"Updated '{new_title or title}'."


@mcp.tool(description="Delete a note permanently.")
async def delete_note(title: str) -> str:
    await _delete(f"/api/notes/{title}")
    return f"Deleted '{title}'."


@mcp.tool(description="Return all tags currently used across notes.")
async def list_tags() -> str:
    data = await _get("/api/tags")
    return json.dumps(data, indent=2)


# ASGI app for `uvicorn memlog_mcp.main:app`
app = mcp.streamable_http_app()
