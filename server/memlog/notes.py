import re
from pathlib import Path

import aiofiles
import aiofiles.os

from .errors import NOTE_EXISTS, NOTE_NOT_FOUND, validate_filename
from .models import Note, SearchResult
from .search import SearchIndex

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')


def _mtime(path: Path) -> float:
    return path.stat().st_mtime


def _to_note(path: Path, content: str | None = None) -> Note:
    return Note(title=path.stem, content=content, last_modified=_mtime(path))


class NoteStore:
    def __init__(self, notes_path: Path, index_path: Path) -> None:
        self._root = notes_path
        self._index = SearchIndex(notes_path, index_path)

    def _path(self, title: str) -> Path:
        return self._root / f"{title}.md"

    async def get(self, title: str) -> Note:
        p = self._path(title)
        if not p.exists():
            raise NOTE_NOT_FOUND
        async with aiofiles.open(p) as f:
            content = await f.read()
        return _to_note(p, content)

    async def create(self, title: str, content: str = "") -> Note:
        title = title.strip()
        validate_filename(title)
        p = self._path(title)
        if p.exists():
            raise NOTE_EXISTS
        async with aiofiles.open(p, "w") as f:
            await f.write(content)
        return _to_note(p, content)

    async def update(self, title: str, new_title: str | None, new_content: str | None) -> Note:
        p = self._path(title)
        if not p.exists():
            raise NOTE_NOT_FOUND

        if new_title is not None:
            new_title = new_title.strip()
            validate_filename(new_title)
            dest = self._path(new_title)
            if dest.exists() and dest != p:
                raise NOTE_EXISTS
            await aiofiles.os.rename(p, dest)
            p = dest

        if new_content is not None:
            async with aiofiles.open(p, "w") as f:
                await f.write(new_content)

        async with aiofiles.open(p) as f:
            content = await f.read()
        return _to_note(p, content)

    async def delete(self, title: str) -> None:
        p = self._path(title)
        if not p.exists():
            raise NOTE_NOT_FOUND
        await aiofiles.os.remove(p)

    def search(
        self,
        term: str,
        sort: str = "score",
        order: str = "desc",
        limit: int = 1000,
    ) -> list[SearchResult]:
        return self._index.search(term, sort=sort, order=order, limit=limit)

    def get_tags(self) -> list[str]:
        return self._index.get_tags()
