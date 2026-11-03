"""Job queries (web.md §6 *API internals*). Functions take a session and never commit."""

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.frames.model import FrameRow
from app.jobs.model import RESTARTED, JobRow, JobState
from app.verify.model import FrameState


async def fail_interrupted(session: AsyncSession) -> int:
    """The restart sweep (web.md §4.1): every QUEUED or RUNNING job becomes FAILED with the
    restart message, its stage kept. Returns how many. A retry is a new job (deploy.md §5)."""
    result = await session.execute(
        update(JobRow)
        .where(JobRow.state.in_([JobState.QUEUED, JobState.RUNNING]))
        .values(state=JobState.FAILED, error=RESTARTED)
    )
    return result.rowcount  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]


async def fail_interrupted_frames(session: AsyncSession) -> int:
    """The frame half of the restart sweep (web.md §4.1, verify.md §5's sweep edges; T021): every
    frame still rendering or auditing died with the process, so it becomes FAILED, `restart`."""
    result = await session.execute(
        update(FrameRow)
        .where(FrameRow.state.in_([FrameState.RENDERING.value, FrameState.AUDITING.value]))
        .values(state=FrameState.FAILED.value, failure="restart", asset=None)
    )
    return result.rowcount  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
