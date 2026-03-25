from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ── Notes ─────────────────────────────────────────────────────────────────────


class Note(_CamelModel):
    title: str
    content: str | None = None
    last_modified: float


class NoteCreate(_CamelModel):
    title: str
    content: str | None = None


class NoteUpdate(_CamelModel):
    new_title: str | None = None
    new_content: str | None = None


class SearchResult(_CamelModel):
    title: str
    last_modified: float
    score: float | None = None
    title_highlights: str | None = None
    content_highlights: str | None = None
    tag_matches: list[str] | None = None


# ── Auth ──────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Attachments ───────────────────────────────────────────────────────────────


class AttachmentCreateResponse(_CamelModel):
    filename: str
    url: str


# ── Config ────────────────────────────────────────────────────────────────────


class ConfigResponse(_CamelModel):
    auth_type: str
    quick_access_hide: bool
    quick_access_title: str
    quick_access_term: str
    quick_access_sort: str
    quick_access_limit: int
    semantic_search_available: bool = False


# ── Version ───────────────────────────────────────────────────────────────────


class VersionResponse(BaseModel):
    version: str
