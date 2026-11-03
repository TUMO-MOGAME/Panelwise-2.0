"""GET /api/v1/files/{path}: an asset by its signed link, in local mode only (Panelwise 2.0).

A `LocalStore` link plays the part of a Supabase Storage signed URL: it names the path, an expiry
and an HMAC of both, so it needs no session and works in an <img> tag. Any link that fails the
check is a 404, whatever the reason: a wrong signature tells a guesser nothing.
"""

from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse

from app.api.errors import ApiError
from app.storage import LocalStore, StorageError

router = APIRouter()

_TYPES = {
    ".png": "image/png",
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
}


@router.get("/files/{path:path}")
async def file(
    request: Request,
    path: str,
    expires: Annotated[int, Query()],
    sig: Annotated[str, Query()],
    download: Annotated[str | None, Query()] = None,
) -> FileResponse:
    store: object = getattr(request.app.state, "store", None)
    if not isinstance(store, LocalStore) or not store.check(path, expires, sig):
        raise ApiError(404, "not_found")
    try:
        target = store.file(path)
    except StorageError:
        raise ApiError(404, "not_found") from None
    if not target.is_file():
        raise ApiError(404, "not_found")
    media_type = _TYPES.get(PurePosixPath(path).suffix.lower(), "application/octet-stream")
    # A download link names the file (downloads.py); otherwise the browser shows it inline.
    return FileResponse(
        target,
        media_type=media_type,
        filename=download,
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
