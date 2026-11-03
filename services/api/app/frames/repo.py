"""Frame queries (web.md §6). Functions take a session and never commit."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.frames.model import AuditTarget, FrameAuditRow, FrameRow


async def frames_of(session: AsyncSession, project_id: uuid.UUID) -> list[FrameRow]:
    rows = await session.execute(
        select(FrameRow)
        .where(FrameRow.project_id == project_id)
        .order_by(FrameRow.scene_index, FrameRow.shot_number)
    )
    return list(rows.scalars())


async def audits_of(
    session: AsyncSession, project_id: uuid.UUID
) -> dict[tuple[int, int], list[FrameAuditRow]]:
    """Every audited attempt of the project's storyboard frames, by frame, oldest attempt first:
    one read over the (project, target, scene, shot, attempt) key (verify.md §6). A comic panel's
    attempts (target comic, T064) are never a storyboard frame's."""
    rows = await session.execute(
        select(FrameAuditRow)
        .where(
            FrameAuditRow.project_id == project_id,
            FrameAuditRow.target == AuditTarget.STORYBOARD.value,
        )
        .order_by(FrameAuditRow.scene_index, FrameAuditRow.shot_number, FrameAuditRow.attempt)
    )
    out: dict[tuple[int, int], list[FrameAuditRow]] = {}
    for a in rows.scalars():
        out.setdefault((a.scene_index, a.shot_number), []).append(a)
    return out
