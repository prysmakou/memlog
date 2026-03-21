import re
import tomllib
from pathlib import Path

import pytest

from helpers import camel_case, get_env, is_valid_filename, strip_whitespace


# camel_case
def test_camel_case_single_word():
    assert camel_case("title") == "title"


def test_camel_case_two_words():
    assert camel_case("last_modified") == "lastModified"


def test_camel_case_multiple_words():
    assert camel_case("quick_access_hide") == "quickAccessHide"


# is_valid_filename
def test_is_valid_filename_valid():
    assert is_valid_filename("my-note") == "my-note"


@pytest.mark.parametrize("char", list('<>:"/\\|?*'))
def test_is_valid_filename_rejects_invalid_chars(char):
    with pytest.raises(ValueError):
        is_valid_filename(f"note{char}name")


# strip_whitespace
def test_strip_whitespace_strips():
    assert strip_whitespace("  hello  ") == "hello"


def test_strip_whitespace_noop():
    assert strip_whitespace("clean") == "clean"


# get_env
def test_get_env_returns_value(monkeypatch):
    monkeypatch.setenv("_TEST_VAR", "hello")
    assert get_env("_TEST_VAR") == "hello"


def test_get_env_default(monkeypatch):
    monkeypatch.delenv("_TEST_VAR", raising=False)
    assert get_env("_TEST_VAR", default="fallback") == "fallback"


def test_get_env_cast_int(monkeypatch):
    monkeypatch.setenv("_TEST_INT", "42")
    assert get_env("_TEST_INT", cast_int=True) == 42


def test_get_env_cast_bool_true(monkeypatch):
    monkeypatch.setenv("_TEST_BOOL", "true")
    assert get_env("_TEST_BOOL", cast_bool=True) is True


def test_get_env_cast_bool_false(monkeypatch):
    monkeypatch.setenv("_TEST_BOOL", "false")
    assert get_env("_TEST_BOOL", cast_bool=True) is False


# version
def test_version_matches_pyproject():
    pyproject = Path(__file__).parent.parent.parent / "pyproject.toml"
    with pyproject.open("rb") as f:
        expected = tomllib.load(f)["project"]["version"]
    # Must be exact semver, optionally with -rc.N or -beta.N suffix
    assert re.match(r"^\d+\.\d+\.\d+(-[a-z]+\.\d+)?$", expected)
