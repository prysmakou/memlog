import io
from pathlib import Path

from fastapi.testclient import TestClient


def test_upload_and_download(client: TestClient, tmp_path: Path) -> None:
    r = client.post(
        "/api/attachments",
        files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["filename"] == "test.txt"
    assert "/attachments/test.txt" in data["url"]

    r = client.get("/api/attachments/test.txt")
    assert r.status_code == 200
    assert r.content == b"hello"


def test_upload_collision_gets_timestamp_suffix(client: TestClient) -> None:
    files = {"file": ("dup.txt", io.BytesIO(b"first"), "text/plain")}
    r1 = client.post("/api/attachments", files=files)
    assert r1.status_code == 201

    files = {"file": ("dup.txt", io.BytesIO(b"second"), "text/plain")}
    r2 = client.post("/api/attachments", files=files)
    assert r2.status_code == 201
    assert r2.json()["filename"] != "dup.txt"
    assert "dup_" in r2.json()["filename"]


def test_download_not_found(client: TestClient) -> None:
    r = client.get("/api/attachments/missing.txt")
    assert r.status_code == 404


def test_attachment_alias_route(client: TestClient) -> None:
    client.post(
        "/api/attachments",
        files={"file": ("alias.txt", io.BytesIO(b"data"), "text/plain")},
    )
    r = client.get("/attachments/alias.txt")
    assert r.status_code == 200


def test_invalid_filename(client: TestClient) -> None:
    r = client.post(
        "/api/attachments",
        files={"file": ("bad/file.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert r.status_code == 400
