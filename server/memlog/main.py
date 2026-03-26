import importlib.metadata
import logging
import os as _os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.status import HTTP_201_CREATED, HTTP_204_NO_CONTENT

from .attachments import AttachmentStore
from .auth import Authenticator, login, print_totp_qr
from .config import AppConfig, AuthType
from .models import (
    AttachmentCreateResponse,
    ConfigResponse,
    LoginRequest,
    Note,
    NoteCreate,
    NoteUpdate,
    SearchResult,
    TokenResponse,
    VersionResponse,
)
from .notes import NoteStore

_VERSION = importlib.metadata.version("memlog")
_DIST = Path("client/dist")
_log = logging.getLogger("memlog")

# ── App factory ───────────────────────────────────────────────────────────────


def create_app(config: AppConfig | None = None) -> FastAPI:
    cfg = config or AppConfig.from_env()
    qdrant_index = None  # may be replaced below; declared here so lifespan can rebind it

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal qdrant_index
        _log.info("Memlog %s", _VERSION)
        if qdrant_index is not None:
            try:
                await qdrant_index._client.get_collections()
                _log.info("Semantic search: Qdrant reachable")
            except Exception as exc:
                _log.warning("Semantic search disabled: cannot reach Qdrant (%s)", exc)
                qdrant_index = None
        if qdrant_index is not None and cfg.voyage_api_key:
            try:
                async with httpx.AsyncClient() as http:
                    r = await http.post(
                        "https://api.voyageai.com/v1/embeddings",
                        headers={"Authorization": f"Bearer {cfg.voyage_api_key}"},
                        json={"model": cfg.embedding_model, "input": ["test"]},
                        timeout=10.0,
                    )
                    r.raise_for_status()
                _log.info("Semantic search: Voyage AI reachable")
            except Exception as exc:
                # Log error type only — do not include exc details which may echo request headers
                _log.warning(
                    "Semantic search disabled: cannot reach Voyage AI (%s: %s)",
                    type(exc).__name__,
                    exc,
                )
                qdrant_index = None
        if cfg.auth_type == AuthType.TOTP and cfg.totp_key:
            print_totp_qr(cfg)
        yield

    app = FastAPI(
        title="Memlog",
        description="Markdown notes for humans, MCP-native for AI agents.",
        version=_VERSION,
        docs_url=f"{cfg.path_prefix}/api/docs",
        openapi_url=f"{cfg.path_prefix}/api/openapi.json",
        lifespan=lifespan,
    )

    notes = NoteStore(cfg.notes_path, cfg.index_path)
    attachments = AttachmentStore(cfg.attachments_path)
    auth = Authenticator(cfg)
    Auth = Annotated[str | None, Depends(auth)]

    if cfg.semantic_search_available:
        from .search_qdrant import QdrantSearchIndex

        try:
            qdrant_index = QdrantSearchIndex(cfg)
        except ImportError as exc:
            raise RuntimeError(str(exc)) from None

    # ── Health & version ──────────────────────────────────────────────────────

    @app.get("/health", include_in_schema=False)
    @app.get(f"{cfg.path_prefix}/health", include_in_schema=False)
    async def health() -> JSONResponse:
        checks: dict[str, str] = {}
        healthy = True

        if not cfg.notes_path.is_dir() or not _os.access(cfg.notes_path, _os.W_OK):
            checks["filesystem"] = "not writable"
            healthy = False
        else:
            checks["filesystem"] = "ok"

        if qdrant_index is not None:
            try:
                await qdrant_index._client.get_collections()
                checks["qdrant"] = "ok"
            except Exception as exc:
                checks["qdrant"] = f"unreachable: {exc}"
                healthy = False

        return JSONResponse(
            {"status": "ok" if healthy else "degraded", "checks": checks},
            status_code=200 if healthy else 503,
        )

    @app.get(f"{cfg.path_prefix}/api/version", response_model=VersionResponse, tags=["meta"])
    async def version() -> VersionResponse:
        return VersionResponse(version=_VERSION)

    @app.get(f"{cfg.path_prefix}/api/config", response_model=ConfigResponse, tags=["meta"])
    async def get_config() -> ConfigResponse:
        return ConfigResponse(
            auth_type=cfg.auth_type.value,
            quick_access_hide=cfg.quick_access_hide,
            quick_access_title=cfg.quick_access_title,
            quick_access_term=cfg.quick_access_term,
            quick_access_sort=cfg.quick_access_sort,
            quick_access_limit=cfg.quick_access_limit,
            semantic_search_available=cfg.semantic_search_available,
        )

    # ── Auth ──────────────────────────────────────────────────────────────────

    if cfg.auth_type.requires_auth():

        @app.post(
            f"{cfg.path_prefix}/api/token",
            response_model=TokenResponse,
            tags=["auth"],
        )
        async def token(body: LoginRequest) -> TokenResponse:
            tok = login(cfg, body.username, body.password)
            return TokenResponse(access_token=tok)

        @app.get(f"{cfg.path_prefix}/api/auth-check", tags=["auth"])
        async def auth_check(_: Auth) -> str:
            return "OK"

    # ── Notes ─────────────────────────────────────────────────────────────────

    @app.get(
        f"{cfg.path_prefix}/api/notes/{{title}}",
        response_model=Note,
        tags=["notes"],
    )
    async def get_note(title: str, _: Auth) -> Note:
        return await notes.get(title)

    @app.get(
        f"{cfg.path_prefix}/api/search",
        response_model=list[SearchResult],
        tags=["notes"],
    )
    async def search(
        _: Auth,
        term: str = "*",
        sort: str = "score",
        order: str = "desc",
        limit: int = 1000,
        semantic: bool = False,
    ) -> list[SearchResult]:
        if semantic and qdrant_index is not None:
            return await qdrant_index.search(term, sort=sort, order=order, limit=limit)
        return notes.search(term, sort=sort, order=order, limit=limit)

    @app.get(f"{cfg.path_prefix}/api/tags", response_model=list[str], tags=["notes"])
    async def get_tags(_: Auth) -> list[str]:
        return notes.get_tags()

    if not cfg.auth_type.is_read_only():

        @app.post(
            f"{cfg.path_prefix}/api/notes",
            response_model=Note,
            status_code=HTTP_201_CREATED,
            tags=["notes"],
        )
        async def create_note(body: NoteCreate, _: Auth) -> Note:
            return await notes.create(body.title, body.content or "")

        @app.patch(
            f"{cfg.path_prefix}/api/notes/{{title}}",
            response_model=Note,
            tags=["notes"],
        )
        async def update_note(title: str, body: NoteUpdate, _: Auth) -> Note:
            return await notes.update(title, body.new_title, body.new_content)

        @app.delete(
            f"{cfg.path_prefix}/api/notes/{{title}}",
            status_code=HTTP_204_NO_CONTENT,
            tags=["notes"],
        )
        async def delete_note(title: str, _: Auth) -> None:
            await notes.delete(title)

    # ── Attachments ───────────────────────────────────────────────────────────

    @app.get(
        f"{cfg.path_prefix}/api/attachments/{{filename}}",
        tags=["attachments"],
    )
    @app.get(f"{cfg.path_prefix}/attachments/{{filename}}", include_in_schema=False)
    async def get_attachment(filename: str, _: Auth) -> FileResponse:
        return attachments.download(filename)

    if not cfg.auth_type.is_read_only():

        @app.post(
            f"{cfg.path_prefix}/api/attachments",
            response_model=AttachmentCreateResponse,
            status_code=HTTP_201_CREATED,
            tags=["attachments"],
        )
        async def upload_attachment(file: UploadFile, _: Auth) -> AttachmentCreateResponse:
            return await attachments.upload(file)

    # ── SPA shell ─────────────────────────────────────────────────────────────

    _index_html: str | None = None

    def _spa() -> HTMLResponse:
        nonlocal _index_html
        if _index_html is None:
            p = _DIST / "index.html"
            if p.exists():
                html = p.read_text()
                if cfg.path_prefix:
                    html = html.replace('<base href="">', f'<base href="{cfg.path_prefix}/">', 1)
                _index_html = html
            else:
                return HTMLResponse("<h1>Frontend not built</h1>", status_code=503)
        return HTMLResponse(_index_html)

    for spa_path in ("/", "/login", "/search", "/new", "/note/{title:path}"):
        full = f"{cfg.path_prefix}{spa_path}"
        app.add_api_route(full, lambda: _spa(), include_in_schema=False)  # noqa: B023

    # ── Static files ──────────────────────────────────────────────────────────

    if _DIST.exists():
        app.mount(
            f"{cfg.path_prefix}/",
            StaticFiles(directory=str(_DIST), html=False),
            name="static",
        )

    return app


# Module-level app for uvicorn (`uvicorn memlog.main:app`).
# Only created when MEMLOG_PATH is present so tests that import create_app
# directly are not affected.
if _os.environ.get("MEMLOG_PATH"):
    app = create_app()
