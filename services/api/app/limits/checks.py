"""The hosted demo's limits as route checks (docs/design/limits.md §4, §6; T069). Each raises
`ApiError` and writes nothing; each is off when its setting is unset or 0."""

import io
import uuid

import pdfplumber
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.core.config import Settings
from app.limits.usage import drawings_this_month, tokens_this_month, uploads_today


def _settings(request: Request) -> Settings:
    return request.app.state.settings


async def budget_spent(request: Request, session: AsyncSession) -> bool:
    """This month's tokens at or over LLM_MONTHLY_TOKEN_CAP. Work already running finishes."""
    cap = _settings(request).llm_monthly_token_cap
    return bool(cap) and await tokens_this_month(session) >= cap  # type: ignore[operator]


async def check_budget(request: Request, session: AsyncSession) -> None:
    if await budget_spent(request, session):
        raise ApiError(429, "llm_budget_spent")


async def images_spent(request: Request, session: AsyncSession) -> bool:
    """This month's drawings at or over IMAGE_MONTHLY_GENERATION_CAP (T030). Work already running
    finishes, as for tokens."""
    cap = _settings(request).image_monthly_generation_cap
    return bool(cap) and await drawings_this_month(session) >= cap  # type: ignore[operator]


async def check_images(request: Request, session: AsyncSession) -> None:
    if await images_spent(request, session):
        raise ApiError(429, "image_budget_spent")


async def check_uploads(request: Request, session: AsyncSession, owner: uuid.UUID) -> None:
    per_day = _settings(request).uploads_per_day
    if per_day and await uploads_today(session, owner) >= per_day:
        raise ApiError(429, "upload_limit", extra={"per_day": per_day})


def check_pages(request: Request, pdf: bytes) -> None:
    """Over UPLOAD_MAX_PAGES → 413. A PDF this can't open is left to the job, whose parse says
    `not_a_pdf` properly (web.md §4.1a). CPU work: the route runs it in a thread."""
    max_pages = _settings(request).upload_max_pages
    if not max_pages:
        return
    try:
        with pdfplumber.open(io.BytesIO(pdf)) as opened:
            pages = len(opened.pages)
    except Exception:
        return
    if pages > max_pages:
        raise ApiError(413, "too_many_pages", extra={"max_pages": max_pages})
