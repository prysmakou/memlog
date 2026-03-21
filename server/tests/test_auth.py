import pytest

from auth.local.local import LocalAuth
from auth.models import Login


@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setenv("MEMLOG_AUTH_TYPE", "password")
    monkeypatch.setenv("MEMLOG_USERNAME", "testuser")
    monkeypatch.setenv("MEMLOG_PASSWORD", "testpass")
    monkeypatch.setenv("MEMLOG_SECRET_KEY", "test-secret-key-1234567890abcdef")
    return LocalAuth()


def test_login_success(auth):
    token = auth.login(Login(username="testuser", password="testpass"))
    assert token.access_token
    assert token.token_type == "bearer"


def test_login_wrong_password(auth):
    with pytest.raises(ValueError):
        auth.login(Login(username="testuser", password="wrongpass"))


def test_login_wrong_username(auth):
    with pytest.raises(ValueError):
        auth.login(Login(username="wronguser", password="testpass"))


def test_login_username_case_insensitive(auth):
    token = auth.login(Login(username="TESTUSER", password="testpass"))
    assert token.access_token


def test_valid_token_validates(auth):
    token = auth.login(Login(username="testuser", password="testpass"))
    auth._validate_token(token.access_token)  # should not raise


def test_invalid_token_raises(auth):
    with pytest.raises(Exception):
        auth._validate_token("not.a.valid.token")


def test_none_token_raises(auth):
    with pytest.raises(Exception):
        auth._validate_token(None)


def test_wrong_secret_raises(auth, monkeypatch):
    token = auth.login(Login(username="testuser", password="testpass"))
    # Create a second auth instance with a different secret
    monkeypatch.setenv("MEMLOG_SECRET_KEY", "completely-different-secret-key!")
    other_auth = LocalAuth()
    with pytest.raises(Exception):
        other_auth._validate_token(token.access_token)
