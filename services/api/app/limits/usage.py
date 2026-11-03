"""What the hosted demo has spent (docs/design/limits.md §3, §4, §6; T069): Token Factory tokens per
calendar month (UTC), and an owner's uploads in the last 24 hours; T030: drawings per month, read
from the audit log."""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import BigInteger, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.frames.model import FrameAuditRow
from app.llm import ChatResult
from app.projects.model import ProjectRow

log = logging.getLogger(__name__)


class LlmUsageRow(Base):
    """One row per month: every answer's prompt + completion tokens, and how many answers."""

    __tablename__ = "llm_usage"

    month: Mapped[date] = mapped_column(primary_key=True)  # the 1st, UTC
    tokens: Mapped[int] = mapped_column(BigInteger(), server_default="0")
    calls: Mapped[int] = mapped_column(server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.clock_timestamp(), onupdate=func.clock_timestamp()
    )


def this_month(now: datetime) -> date:
    """The 1st of `now`'s month in UTC: a budget month is the same everywhere."""
    utc = now.astimezone(UTC)
    return date(utc.year, utc.month, 1)


async def record_usage(sessions: async_sessionmaker[AsyncSession], result: ChatResult) -> None:
    """Add one answer's tokens to this month. Never raises: a lost count under-counts a little, a
    failed call would lose the work (limits.md §4)."""
    tokens = result.usage.prompt_tokens + result.usage.completion_tokens
    month = this_month(datetime.now(UTC))
    try:
        async with sessions() as session, session.begin():
            upsert = insert(LlmUsageRow).values(month=month, tokens=tokens, calls=1)
            await session.execute(
                upsert.on_conflict_do_update(
                    index_elements=[LlmUsageRow.month],
                    set_={
                        "tokens": LlmUsageRow.tokens + tokens,
                        "calls": LlmUsageRow.calls + 1,
                        "updated_at": func.clock_timestamp(),
                    },
                )
            )
    except Exception:
        log.warning("%d tokens of %s not counted", tokens, result.model, exc_info=True)


async def tokens_this_month(session: AsyncSession) -> int:
    month = this_month(datetime.now(UTC))
    found = await session.scalar(select(LlmUsageRow.tokens).where(LlmUsageRow.month == month))
    return found or 0


async def drawings_this_month(session: AsyncSession) -> int:
    """The drawings logged this UTC month, storyboard and comic (T030): every drawing the API pays
    for is audited and every audit is logged, so the log is the count. A floor: a safety redraw
    is one row, and a restart between a drawing and its log leaves none (limits.md §4)."""
    first = this_month(datetime.now(UTC))
    since = datetime(first.year, first.month, 1, tzinfo=UTC)
    count = await session.scalar(
        select(func.count()).select_from(FrameAuditRow).where(FrameAuditRow.created_at >= since)
    )
    return count or 0


async def uploads_today(session: AsyncSession, owner: uuid.UUID) -> int:
    """The owner's projects created in the last 24 hours (rolling: no time zone decides "today").
    The judge seed's copies keep their source's `created_at`, so the sample never counts."""
    since = datetime.now(UTC) - timedelta(hours=24)
    count = await session.scalar(
        select(func.count())
        .select_from(ProjectRow)
        .where(ProjectRow.owner == owner, ProjectRow.created_at > since)
    )
    return count or 0
