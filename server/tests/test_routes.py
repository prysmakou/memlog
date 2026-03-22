from pathlib import Path

from fastapi.testclient import TestClient

from memlog.config import AuthType
from memlog.main import create_app

from .conftest import make_config


def test_health(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


def test_version(client: TestClient) -> None:
    r = client.get("/api/version")
    assert r.status_code == 200
    assert "version" in r.json()


def test_config(client: TestClient) -> None:
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "authType" in data
    assert "quickAccessHide" in data


def test_config_reflects_auth_type(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, auth_type=AuthType.READ_ONLY)
    c = TestClient(create_app(cfg))
    r = c.get("/api/config")
    assert r.json()["authType"] == "read_only"


def test_read_only_allows_reads(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, auth_type=AuthType.READ_ONLY)
    c = TestClient(create_app(cfg))
    r = c.get("/api/search?term=*")
    assert r.status_code == 200


def test_read_only_blocks_writes(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, auth_type=AuthType.READ_ONLY)
    c = TestClient(create_app(cfg))
    r = c.post("/api/notes", json={"title": "x", "content": ""})
    assert r.status_code == 404  # route not registered


def test_search_empty_vault(client: TestClient) -> None:
    r = client.get("/api/search?term=*")
    assert r.status_code == 200
    assert r.json() == []


def test_tags_empty(client: TestClient) -> None:
    r = client.get("/api/tags")
    assert r.status_code == 200
    assert r.json() == []
