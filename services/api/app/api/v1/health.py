"""GET /api/v1/health: are the datastores this API depends on reachable?

Docker's healthcheck and the web app's /api/health both read it. A failing check reports
only the exception's type: its message can carry a connection string, and this endpoint
is public.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

type Check = Callable[[], Awaitable[None]]

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, str]


def get_checks(request: Request) -> dict[str, Check]:
    checks: dict[str, Check] = request.app.state.health_checks
    return checks


async def _run(check: Check, timeout_s: float) -> str:
    try:
        await asyncio.wait_for(check(), timeout=timeout_s)
    except Exception as exc:
        return f"error: {type(exc).__name__}"
    return "ok"


@router.get("/health")
async def health(
    request: Request, response: Response, checks: Annotated[dict[str, Check], Depends(get_checks)]
) -> HealthResponse:
    timeout_s: float = request.app.state.settings.health_check_timeout_s

    names = list(checks)
    results = await asyncio.gather(*(_run(checks[n], timeout_s) for n in names))
    body = HealthResponse(
        status="ok" if all(r == "ok" for r in results) else "degraded",
        checks=dict(zip(names, results, strict=True)),
    )
    if body.status != "ok":
        response.status_code = 503
    return body
