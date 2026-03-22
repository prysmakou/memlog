import re

from fastapi import HTTPException

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')


def validate_filename(name: str) -> None:
    if _INVALID_CHARS.search(name):
        raise HTTPException(status_code=400, detail="Title contains invalid characters.")


NOTE_NOT_FOUND = HTTPException(status_code=404, detail="The specified note cannot be found.")
NOTE_EXISTS = HTTPException(
    status_code=409, detail="Cannot create note. A note with the same title already exists."
)
ATTACHMENT_NOT_FOUND = HTTPException(
    status_code=404, detail="The specified attachment cannot be found."
)
ATTACHMENT_EXISTS = HTTPException(
    status_code=409,
    detail="Cannot create attachment. An attachment with the same filename already exists.",
)
LOGIN_FAILED = HTTPException(status_code=401, detail="Invalid login details.")
UNAUTHORIZED = HTTPException(status_code=401, detail="Not authenticated.")
