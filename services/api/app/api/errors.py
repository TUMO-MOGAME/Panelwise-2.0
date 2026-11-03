"""The API's error shape: `{"error": "<code>"}` with a status (web.md §6). Raised anywhere in a
request; `install` registers the handler that turns it into the response."""

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        *,
        headers: Mapping[str, str] | None = None,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.headers = dict(headers or {})
        # Fields beside "error" that the web's copy needs, e.g. a limit's figure (T069).
        self.extra = dict(extra or {})


async def _respond(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    body = {**exc.extra, "error": exc.code}
    return JSONResponse(body, status_code=exc.status, headers=exc.headers)


def install(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _respond)
