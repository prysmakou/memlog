from pathlib import Path

from memlog.search import SearchIndex, _extract_tags, _preprocess_query

# ── Tag extraction ────────────────────────────────────────────────────────────


def test_extract_tags_basic() -> None:
    _, tags = _extract_tags("hello #world and #foo")
    assert "world" in tags
    assert "foo" in tags


def test_extract_tags_lowercases() -> None:
    _, tags = _extract_tags("#Python is #GREAT")
    assert "python" in tags
    assert "great" in tags


def test_extract_tags_ignores_code_spans() -> None:
    _, tags = _extract_tags("text `#notag` and #realtag")
    assert "notag" not in tags
    assert "realtag" in tags


def test_extract_tags_removes_from_content() -> None:
    content, _ = _extract_tags("some #tag text")
    assert "#tag" not in content


# ── Query preprocessing ───────────────────────────────────────────────────────


def test_preprocess_hashtag() -> None:
    assert "tags:python" in _preprocess_query("#python")


def test_preprocess_no_hashtag() -> None:
    assert _preprocess_query("python") == "python"


def test_preprocess_mixed() -> None:
    result = _preprocess_query("notes #python")
    assert "tags:python" in result
    assert "notes" in result


# ── SearchIndex ───────────────────────────────────────────────────────────────


def test_search_finds_note(tmp_path: Path) -> None:
    (tmp_path / "rust.md").write_text("Rust is a systems language")
    idx = SearchIndex(tmp_path, tmp_path / ".idx")
    results = idx.search("systems")
    assert any(r.title == "rust" for r in results)


def test_search_wildcard_returns_all(tmp_path: Path) -> None:
    (tmp_path / "note1.md").write_text("first")
    (tmp_path / "note2.md").write_text("second")
    idx = SearchIndex(tmp_path, tmp_path / ".idx")
    assert len(idx.search("*")) == 2


def test_search_no_results(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text("hello world")
    idx = SearchIndex(tmp_path, tmp_path / ".idx")
    assert idx.search("xyzzy_nonexistent") == []


def test_search_limit(tmp_path: Path) -> None:
    for i in range(5):
        (tmp_path / f"note{i}.md").write_text("common keyword")
    idx = SearchIndex(tmp_path, tmp_path / ".idx")
    assert len(idx.search("common", limit=3)) == 3


def test_search_by_tag(tmp_path: Path) -> None:
    (tmp_path / "tagged.md").write_text("some content #mytag")
    (tmp_path / "plain.md").write_text("other content")
    idx = SearchIndex(tmp_path, tmp_path / ".idx")
    results = idx.search("#mytag")
    assert len(results) == 1
    assert results[0].title == "tagged"


def test_get_tags(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("content #alpha")
    (tmp_path / "b.md").write_text("content #beta")
    idx = SearchIndex(tmp_path, tmp_path / ".idx")
    tags = idx.get_tags()
    assert "alpha" in tags
    assert "beta" in tags


def test_search_syncs_new_note(tmp_path: Path) -> None:
    idx = SearchIndex(tmp_path, tmp_path / ".idx")
    assert idx.search("newword") == []
    (tmp_path / "late.md").write_text("newword content")
    results = idx.search("newword")
    assert any(r.title == "late" for r in results)


def test_search_detects_deleted_note(tmp_path: Path) -> None:
    p = tmp_path / "gone.md"
    p.write_text("unique_term_xyz")
    idx = SearchIndex(tmp_path, tmp_path / ".idx")
    assert idx.search("unique_term_xyz")
    p.unlink()
    assert idx.search("unique_term_xyz") == []


def test_schema_version_rebuild(tmp_path: Path) -> None:
    idx_path = tmp_path / ".idx"
    SearchIndex(tmp_path, idx_path)
    # Corrupt the version file to trigger a rebuild
    (idx_path / ".schema_version").write_text("0")
    # Should rebuild without error
    SearchIndex(tmp_path, idx_path)
    from memlog.search import _SCHEMA_VERSION

    assert (idx_path / ".schema_version").read_text() == _SCHEMA_VERSION
