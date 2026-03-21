"""Memlog MCP server — exposes Memlog notes as Claude Code tools."""

import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

MEMLOG_URL = os.environ.get("MEMLOG_URL", "http://localhost:8080").rstrip("/")

mcp = FastMCP("Memlog")


def _client() -> httpx.Client:
    headers = {}
    token = os.environ.get("MEMLOG_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=MEMLOG_URL, headers=headers, timeout=10)


def _authed_client() -> httpx.Client:
    """Return a client, logging in first if credentials are provided."""
    token = os.environ.get("MEMLOG_TOKEN")
    if not token:
        username = os.environ.get("MEMLOG_USERNAME")
        password = os.environ.get("MEMLOG_PASSWORD")
        if username and password:
            r = httpx.post(
                f"{MEMLOG_URL}/api/token",
                json={"username": username, "password": password},
                timeout=10,
            )
            r.raise_for_status()
            token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=MEMLOG_URL, headers=headers, timeout=10)


@mcp.tool()
def search_notes(
    term: str,
    sort: str = "score",
    order: str = "desc",
    limit: Optional[int] = None,
) -> list[dict]:
    """Search notes by keyword, phrase, or #tag.

    Args:
        term: Search term. Use #tagname for tag search, "phrase" for exact
            match, or * for all notes.
        sort: Sort by 'score', 'title', or 'lastModified'. Default 'score'.
        order: 'asc' or 'desc'. Default 'desc'.
        limit: Maximum number of results to return.
    """
    params = {"term": term, "sort": sort, "order": order}
    if limit is not None:
        params["limit"] = limit
    with _authed_client() as client:
        r = client.get("/api/search", params=params)
        r.raise_for_status()
        return r.json()


@mcp.tool()
def get_note(title: str) -> dict:
    """Get the full content of a note by title.

    Args:
        title: Exact note title (without .md extension).
    """
    with _authed_client() as client:
        r = client.get(f"/api/notes/{title}")
        r.raise_for_status()
        return r.json()


@mcp.tool()
def create_note(title: str, content: str = "") -> dict:
    """Create a new note.

    Args:
        title: Note title. Cannot contain <>:"/\\|?* characters.
        content: Note content in Markdown.
    """
    with _authed_client() as client:
        r = client.post(
            "/api/notes", json={"title": title, "content": content}
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
def update_note(
    title: str,
    new_content: Optional[str] = None,
    new_title: Optional[str] = None,
) -> dict:
    """Update an existing note's content or title.

    Args:
        title: Current note title.
        new_content: Replacement content in Markdown. Omit to keep existing.
        new_title: New title to rename the note. Omit to keep existing.
    """
    body = {}
    if new_content is not None:
        body["newContent"] = new_content
    if new_title is not None:
        body["newTitle"] = new_title
    with _authed_client() as client:
        r = client.patch(f"/api/notes/{title}", json=body)
        r.raise_for_status()
        return r.json()


@mcp.tool()
def delete_note(title: str) -> str:
    """Delete a note permanently.

    Args:
        title: Exact note title to delete.
    """
    with _authed_client() as client:
        r = client.delete(f"/api/notes/{title}")
        r.raise_for_status()
        return f"Deleted '{title}'."


@mcp.tool()
def list_tags() -> list[str]:
    """Return all tags currently used across notes."""
    with _authed_client() as client:
        r = client.get("/api/tags")
        r.raise_for_status()
        return r.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
