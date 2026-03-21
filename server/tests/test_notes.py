import pytest
from pydantic import ValidationError

from notes.file_system.file_system import FileSystemNotes
from notes.models import NoteCreate, NoteUpdate


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMLOG_PATH", str(tmp_path))
    return FileSystemNotes()


# --- CRUD ---

def test_create_and_get(storage):
    storage.create(NoteCreate(title="hello", content="world"))
    note = storage.get("hello")
    assert note.title == "hello"
    assert note.content == "world"


def test_create_returns_note(storage):
    note = storage.create(NoteCreate(title="test", content="body"))
    assert note.title == "test"
    assert note.content == "body"
    assert note.last_modified > 0


def test_create_duplicate_raises(storage):
    storage.create(NoteCreate(title="dup", content=""))
    with pytest.raises(FileExistsError):
        storage.create(NoteCreate(title="dup", content=""))


def test_create_invalid_title_raises():
    with pytest.raises(ValidationError):
        NoteCreate(title="bad<title", content="")


def test_create_strips_whitespace_from_title():
    note = NoteCreate(title="  trimmed  ", content="")
    assert note.title == "trimmed"


def test_get_missing_raises(storage):
    with pytest.raises(FileNotFoundError):
        storage.get("nonexistent")


def test_get_invalid_title_raises(storage):
    with pytest.raises(ValueError):
        storage.get("bad<title")


def test_update_content(storage):
    storage.create(NoteCreate(title="orig", content="old"))
    note = storage.update("orig", NoteUpdate(new_content="new"))
    assert note.content == "new"


def test_update_title(storage):
    storage.create(NoteCreate(title="old-title", content="body"))
    note = storage.update("old-title", NoteUpdate(new_title="new-title"))
    assert note.title == "new-title"
    with pytest.raises(FileNotFoundError):
        storage.get("old-title")
    assert storage.get("new-title").content == "body"


def test_update_title_and_content(storage):
    storage.create(NoteCreate(title="a", content="old"))
    note = storage.update("a", NoteUpdate(new_title="b", new_content="new"))
    assert note.title == "b"
    assert note.content == "new"


def test_update_title_conflict_raises(storage):
    storage.create(NoteCreate(title="a", content=""))
    storage.create(NoteCreate(title="b", content=""))
    with pytest.raises(FileExistsError):
        storage.update("a", NoteUpdate(new_title="b"))


def test_update_missing_raises(storage):
    # No new_title and no new_content → falls through to _read_file → FileNotFoundError
    with pytest.raises(FileNotFoundError):
        storage.update("nonexistent", NoteUpdate())


def test_update_invalid_title_raises(storage):
    with pytest.raises(ValueError):
        storage.update("bad<title", NoteUpdate(new_content="x"))


def test_delete_note(storage):
    storage.create(NoteCreate(title="to-delete", content=""))
    storage.delete("to-delete")
    with pytest.raises(FileNotFoundError):
        storage.get("to-delete")


def test_delete_missing_raises(storage):
    with pytest.raises(FileNotFoundError):
        storage.delete("nonexistent")


def test_delete_invalid_title_raises(storage):
    with pytest.raises(ValueError):
        storage.delete("bad<title")


# --- Search ---

def test_search_finds_note(storage):
    storage.create(NoteCreate(title="py-note", content="python is great"))
    results = storage.search("python")
    assert any(r.title == "py-note" for r in results)


def test_search_wildcard_returns_all(storage):
    storage.create(NoteCreate(title="n1", content=""))
    storage.create(NoteCreate(title="n2", content=""))
    results = storage.search("*")
    assert len(results) == 2


def test_search_no_results(storage):
    storage.create(NoteCreate(title="note", content="hello"))
    results = storage.search("xyzzy_nonexistent")
    assert results == ()


def test_search_limit(storage):
    for i in range(5):
        storage.create(NoteCreate(title=f"note{i}", content="common content"))
    results = storage.search("*", limit=3)
    assert len(results) == 3


def test_search_by_tag(storage):
    storage.create(NoteCreate(title="tagged", content="hello #mytag world"))
    results = storage.search("#mytag")
    assert any(r.title == "tagged" for r in results)


# --- Tag extraction ---

def test_extract_tags_basic():
    _, tags = FileSystemNotes._extract_tags("hello #world #foo")
    assert tags == {"world", "foo"}


def test_extract_tags_lowercases():
    _, tags = FileSystemNotes._extract_tags("#Python #GREAT")
    assert "python" in tags
    assert "great" in tags


def test_extract_tags_ignores_codeblock():
    _, tags = FileSystemNotes._extract_tags("text `#notag` #realtag")
    assert "notag" not in tags
    assert "realtag" in tags


def test_extract_tags_removes_from_content():
    content, _ = FileSystemNotes._extract_tags("hello #tag world")
    assert "#tag" not in content


def test_get_tags(storage):
    storage.create(NoteCreate(title="tagged", content="some #alpha #beta content"))
    tags = storage.get_tags()
    assert "alpha" in tags
    assert "beta" in tags


# --- Search term pre-processing ---

def test_pre_process_replaces_hashtag():
    assert FileSystemNotes._pre_process_search_term("#python") == "tags:python"


def test_pre_process_no_hashtag():
    assert FileSystemNotes._pre_process_search_term("python") == "python"


def test_pre_process_strips_whitespace():
    assert FileSystemNotes._pre_process_search_term("  hello  ") == "hello"


def test_pre_process_mixed():
    result = FileSystemNotes._pre_process_search_term("notes #python")
    assert "tags:python" in result
