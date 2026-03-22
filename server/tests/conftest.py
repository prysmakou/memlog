from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memlog.config import AppConfig, AuthType
from memlog.main import create_app


def make_config(tmp_path: Path, auth_type: AuthType = AuthType.NONE, **kw: object) -> AppConfig:
    return AppConfig(
        notes_path=tmp_path,
        auth_type=auth_type,
        username=kw.get("username"),  # type: ignore[arg-type]
        password=kw.get("password"),  # type: ignore[arg-type]
        secret_key=kw.get("secret_key"),  # type: ignore[arg-type]
        session_expiry_days=30,
        totp_key=kw.get("totp_key"),  # type: ignore[arg-type]
        path_prefix="",
        quick_access_hide=False,
        quick_access_title="RECENTLY MODIFIED",
        quick_access_term="*",
        quick_access_sort="lastModified",
        quick_access_limit=4,
    )


@pytest.fixture
def notes_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    cfg = make_config(tmp_path)
    return TestClient(create_app(cfg))


@pytest.fixture
def auth_client(tmp_path: Path) -> TestClient:
    cfg = make_config(
        tmp_path,
        auth_type=AuthType.PASSWORD,
        username="admin",
        password="secret",
        secret_key="test-secret-key-long-enough",
    )
    return TestClient(create_app(cfg))
