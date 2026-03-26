import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class AuthType(StrEnum):
    NONE = "none"
    READ_ONLY = "read_only"
    PASSWORD = "password"
    TOTP = "totp"

    def requires_auth(self) -> bool:
        return self in (AuthType.PASSWORD, AuthType.TOTP)

    def is_read_only(self) -> bool:
        return self == AuthType.READ_ONLY


def _env(key: str) -> str | None:
    v = os.environ.get(key, "").strip()
    return v if v else None


def _env_bool(key: str, default: bool = False) -> bool:
    v = (_env(key) or "").lower()
    if v in ("true", "1", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key) or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class AppConfig:
    notes_path: Path
    auth_type: AuthType
    username: str | None
    password: str | None
    secret_key: str | None
    session_expiry_days: int
    totp_key: str | None
    path_prefix: str
    quick_access_hide: bool
    quick_access_title: str
    quick_access_term: str
    quick_access_sort: str
    quick_access_limit: int

    qdrant_url: str | None = None
    qdrant_collection: str = "memlog"
    ollama_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    voyage_api_key: str | None = None

    @property
    def semantic_search_available(self) -> bool:
        return self.qdrant_url is not None

    @property
    def index_path(self) -> Path:
        return self.notes_path / ".memlog"

    @property
    def attachments_path(self) -> Path:
        return self.notes_path / "attachments"

    @classmethod
    def from_env(cls) -> "AppConfig":
        raw_path = _env("MEMLOG_PATH")
        if not raw_path:
            raise RuntimeError("MEMLOG_PATH is required")
        notes_path = Path(raw_path)
        if not notes_path.exists():
            raise RuntimeError(f"MEMLOG_PATH '{raw_path}' does not exist")

        auth_type_str = _env("MEMLOG_AUTH_TYPE") or "password"
        try:
            auth_type = AuthType(auth_type_str)
        except ValueError as exc:
            raise RuntimeError(f"Unknown MEMLOG_AUTH_TYPE '{auth_type_str}'") from exc

        path_prefix = _env("MEMLOG_PATH_PREFIX") or ""
        if path_prefix:
            if not path_prefix.startswith("/"):
                raise RuntimeError("MEMLOG_PATH_PREFIX must start with '/'")
            if path_prefix.endswith("/"):
                raise RuntimeError("MEMLOG_PATH_PREFIX must not end with '/'")

        quick_access_sort = _env("MEMLOG_QUICK_ACCESS_SORT") or "lastModified"
        if quick_access_sort not in ("score", "title", "lastModified"):
            raise RuntimeError(
                "MEMLOG_QUICK_ACCESS_SORT must be one of: score, title, lastModified"
            )

        # Support deprecated alias
        quick_access_hide = _env_bool("MEMLOG_QUICK_ACCESS_HIDE") or _env_bool(
            "MEMLOG_HIDE_RECENTLY_MODIFIED"
        )

        return cls(
            notes_path=notes_path,
            auth_type=auth_type,
            qdrant_url=_env("MEMLOG_QDRANT_URL"),
            qdrant_collection=_env("MEMLOG_QDRANT_COLLECTION") or "memlog",
            ollama_url=_env("MEMLOG_OLLAMA_URL") or "http://localhost:11434",
            embedding_model=_env("MEMLOG_EMBEDDING_MODEL") or "nomic-embed-text",
            voyage_api_key=_env("MEMLOG_VOYAGE_API_KEY"),
            username=_env("MEMLOG_USERNAME"),
            password=_env("MEMLOG_PASSWORD"),
            secret_key=_env("MEMLOG_SECRET_KEY"),
            session_expiry_days=_env_int("MEMLOG_SESSION_EXPIRY_DAYS", 30),
            totp_key=_env("MEMLOG_TOTP_KEY"),
            path_prefix=path_prefix,
            quick_access_hide=quick_access_hide,
            quick_access_title=_env("MEMLOG_QUICK_ACCESS_TITLE") or "RECENTLY MODIFIED",
            quick_access_term=_env("MEMLOG_QUICK_ACCESS_TERM") or "*",
            quick_access_sort=quick_access_sort,
            quick_access_limit=_env_int("MEMLOG_QUICK_ACCESS_LIMIT", 4),
        )
