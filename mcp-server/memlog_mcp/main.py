import json
import os
from contextvars import ContextVar
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import PlainTextResponse

_BASE_URL = (os.environ.get("MEMLOG_URL") or "http://localhost:8080").rstrip("/")

_request_token: ContextVar[str | None] = ContextVar("_request_token", default=None)


class _BearerAuthMiddleware:
    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path == "/health":
                await PlainTextResponse("OK")(scope, receive, send)
                return
            headers = dict(scope.get("headers", []))
            auth = headers.get(b"authorization", b"").decode()
            if not auth.startswith("Bearer ") or not auth[len("Bearer ") :].strip():
                await PlainTextResponse("Unauthorized", status_code=401)(
                    scope, receive, send
                )
                return
            _request_token.set(auth[len("Bearer ") :])
        await self._app(scope, receive, send)


mcp = FastMCP(
    "Memlog",
    instructions=(
        "Read and write Memlog notes over HTTP. "
        "Tools: list_notes, search_notes, get_note, create_note, "
        "append_to_note, update_note, delete_note, list_tags."
    ),
    # DNS rebinding protection is redundant when bearer token auth is enforced
    # by the middleware — and it blocks legitimate network requests.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _headers() -> dict[str, str]:
    token = _request_token.get()
    return {"Authorization": f"Bearer {token}"} if token else {}


async def _get(path: str, params: dict | None = None) -> object:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{_BASE_URL}{path}", params=params, headers=_headers())
        r.raise_for_status()
        return r.json()


async def _post(path: str, body: dict) -> object:
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{_BASE_URL}{path}", json=body, headers=_headers())
        r.raise_for_status()
        return r.json()


async def _patch(path: str, body: dict) -> object:
    async with httpx.AsyncClient() as client:
        r = await client.patch(f"{_BASE_URL}{path}", json=body, headers=_headers())
        r.raise_for_status()
        return r.json()


async def _delete(path: str) -> None:
    async with httpx.AsyncClient() as client:
        r = await client.delete(f"{_BASE_URL}{path}", headers=_headers())
        r.raise_for_status()


@mcp.tool(
    description="List all notes with title and lastModified timestamp (no content)."
)
async def list_notes(
    sort: str = "lastModified",
    order: str = "desc",
    limit: int = 50,
) -> str:
    data = await _get(
        "/api/search", {"term": "*", "sort": sort, "order": order, "limit": limit}
    )
    notes = [{"title": n["title"], "lastModified": n["lastModified"]} for n in data]  # type: ignore[index,union-attr,attr-defined]
    return json.dumps(notes, indent=2)


@mcp.tool(description="Search notes by keyword, phrase, or #tag. Use * for all notes.")
async def search_notes(
    term: str,
    sort: str = "score",
    order: str = "desc",
    limit: int = 20,
) -> str:
    data = await _get(
        "/api/search", {"term": term, "sort": sort, "order": order, "limit": limit}
    )
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
    await _patch(
        f"/api/notes/{title}", {"newContent": f"{current}{separator}{content}"}
    )
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
app = _BearerAuthMiddleware(mcp.streamable_http_app())
