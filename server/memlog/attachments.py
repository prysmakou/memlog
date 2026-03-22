from datetime import UTC, datetime
from pathlib import Path

import aiofiles
import aiofiles.os
from fastapi import UploadFile
from fastapi.responses import FileResponse

from .errors import ATTACHMENT_EXISTS, ATTACHMENT_NOT_FOUND, validate_filename
from .models import AttachmentCreateResponse


class AttachmentStore:
    def __init__(self, attachments_path: Path) -> None:
        self._root = attachments_path
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, filename: str) -> Path:
        return self._root / filename

    async def upload(self, file: UploadFile) -> AttachmentCreateResponse:
        filename = file.filename or "upload"
        validate_filename(filename)

        dest = self._path(filename)
        if dest.exists():
            # Append timestamp suffix before extension to avoid collision
            stem = Path(filename).stem
            suffix = Path(filename).suffix
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
            filename = f"{stem}_{ts}{suffix}"
            dest = self._path(filename)
            if dest.exists():
                raise ATTACHMENT_EXISTS

        content = await file.read()
        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)

        return AttachmentCreateResponse(filename=filename, url=f"/attachments/{filename}")

    def download(self, filename: str) -> FileResponse:
        p = self._path(filename)
        if not p.exists():
            raise ATTACHMENT_NOT_FOUND
        return FileResponse(str(p), filename=filename)
