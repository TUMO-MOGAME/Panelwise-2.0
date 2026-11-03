"""T069: the monthly token count and the day's uploads (docs/design/limits.md §3, §4, §6)."""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.limits.usage import LlmUsageRow, record_usage, this_month, tokens_this_month, uploads_today
from app.llm import ChatResult, Tier, Usage
from app.projects.model import ProjectRow
from app.projects.repo import create_upload

pytestmark = pytest.mark.db


def result(prompt: int, completion: int, reasoning: int = 0) -> ChatResult:
    return ChatResult("ok", "m", Tier.FAST, Usage(prompt, completion, reasoning), "stop")


def test_a_blank_cap_in_the_environment_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # .env.example lists LLM_MONTHLY_TOKEN_CAP= with no value; the API must still start.
    from app.core.config import Settings

    for name in ("LLM_MONTHLY_TOKEN_CAP", "UPLOADS_PER_DAY", "UPLOAD_MAX_PAGES"):
        monkeypatch.setenv(name, "")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert (
        settings.llm_monthly_token_cap,
        settings.uploads_per_day,
        settings.upload_max_pages,
    ) == (
        None,
        None,
        None,
    )
    monkeypatch.setenv("UPLOADS_PER_DAY", "3")
    assert Settings(_env_file=None).uploads_per_day == 3  # type: ignore[call-arg]


def test_this_month_is_the_first_in_utc() -> None:
    assert this_month(datetime(2026, 10, 31, 23, 30, tzinfo=UTC)) == date(2026, 10, 1)
    # 01:30 on 1 Nov in Johannesburg is still October in UTC.
    sast = datetime(2026, 11, 1, 1, 30, tzinfo=UTC) + timedelta(hours=-2)
    assert this_month(sast) == date(2026, 10, 1)


async def test_each_answer_adds_its_prompt_and_completion_tokens_to_the_month(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await record_usage(sessions, result(100, 40, reasoning=30))  # reasoning is part of completion
    await record_usage(sessions, result(5, 2))
    async with sessions() as s:
        assert await tokens_this_month(s) == 147
        row = await s.get(LlmUsageRow, this_month(datetime.now(UTC)))
    assert row is not None and row.calls == 2


async def test_a_new_month_starts_from_zero(sessions: async_sessionmaker[AsyncSession]) -> None:
    await record_usage(sessions, result(10, 10))
    async with sessions() as s, s.begin():
        await s.execute(update(LlmUsageRow).values(month=date(2000, 1, 1)))
    async with sessions() as s:
        assert await tokens_this_month(s) == 0


async def test_a_failed_count_is_logged_and_never_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken() -> AsyncSession:
        raise RuntimeError("the database went away")

    caplog.set_level(logging.WARNING, logger="app.limits.usage")
    await record_usage(broken, result(1, 1))  # type: ignore[arg-type]
    assert any("not counted" in r.getMessage() for r in caplog.records)


async def test_uploads_today_counts_the_owners_projects_of_the_last_24_hours(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    me, someone = uuid.uuid4(), uuid.uuid4()
    async with sessions() as s, s.begin():
        for owner in (me, me, someone):
            pid = uuid.uuid4()
            await create_upload(
                s, project_id=pid, owner=owner, title="t", pdf_path=f"scripts/{pid}.pdf"
            )
        old = uuid.uuid4()
        await create_upload(s, project_id=old, owner=me, title="old", pdf_path="scripts/old.pdf")
        await s.execute(
            update(ProjectRow)
            .where(ProjectRow.id == old)
            .values(created_at=datetime.now(UTC) - timedelta(hours=25))
        )
    async with sessions() as s:
        assert await uploads_today(s, me) == 2
        assert await uploads_today(s, someone) == 1
        assert await uploads_today(s, uuid.uuid4()) == 0
