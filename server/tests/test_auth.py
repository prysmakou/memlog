from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memlog.auth import login, validate_token
from memlog.config import AuthType

from .conftest import make_config


def test_login_success(tmp_path: Path) -> None:
    cfg = make_config(
        tmp_path,
        auth_type=AuthType.PASSWORD,
        username="admin",
        password="secret",
        secret_key="test-key-long-enough-32-chars!!!",
    )
    token = login(cfg, "admin", "secret")
    assert token
    user = validate_token(cfg, token)
    assert user == "admin"


def test_login_wrong_password(tmp_path: Path) -> None:
    cfg = make_config(
        tmp_path,
        auth_type=AuthType.PASSWORD,
        username="admin",
        password="secret",
        secret_key="test-key-long-enough-32-chars!!!",
    )
    with pytest.raises(Exception) as exc:
        login(cfg, "admin", "wrong")
    assert exc.value.status_code == 401  # type: ignore[attr-defined]


def test_login_wrong_username(tmp_path: Path) -> None:
    cfg = make_config(
        tmp_path,
        auth_type=AuthType.PASSWORD,
        username="admin",
        password="secret",
        secret_key="test-key-long-enough-32-chars!!!",
    )
    with pytest.raises(Exception) as exc:
        login(cfg, "hacker", "secret")
    assert exc.value.status_code == 401  # type: ignore[attr-defined]


def test_invalid_token(tmp_path: Path) -> None:
    cfg = make_config(
        tmp_path,
        auth_type=AuthType.PASSWORD,
        username="admin",
        password="secret",
        secret_key="test-key-long-enough-32-chars!!!",
    )
    with pytest.raises(Exception) as exc:
        validate_token(cfg, "not.a.token")
    assert exc.value.status_code == 401  # type: ignore[attr-defined]


def test_auth_route_protected(auth_client: TestClient) -> None:
    r = auth_client.get("/api/notes/anything")
    assert r.status_code == 401


def test_auth_route_with_token(auth_client: TestClient) -> None:
    r = auth_client.post("/api/token", json={"username": "admin", "password": "secret"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = auth_client.get("/api/auth-check", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_auth_token_via_cookie(auth_client: TestClient) -> None:
    r = auth_client.post("/api/token", json={"username": "admin", "password": "secret"})
    token = r.json()["access_token"]
    auth_client.cookies.set("token", token)
    r = auth_client.get("/api/auth-check")
    assert r.status_code == 200
