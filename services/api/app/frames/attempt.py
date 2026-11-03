""" "Try another render": one more audited attempt on a withheld or failed frame (T066; web.md
§6, "Try another render, in order"; T021). The endpoint starts it; this runs it in the
background, like the upload's job (web.md §4.1), and always leaves the frame and its job in a
settled state.
"""

import logging
import uuid
from collections.abc import Callable

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.frames.writer import FrameWriter, frame_hooks
from app.grounding import Extraction
from app.jobs import JobRow, JobState
from app.llm import NebiusChatModel
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.job import fail_job
from app.projects.model import ProjectRow
from app.projects.pipeline import Stage
from app.script import Screenplay
from app.verify.loop import render_until_accepted
from app.verify.model import Check, FrameState, RecordingRenderer

log = logging.getLogger(__name__)

# A fresh renderer per attempt, for that project's screenplay and extraction, in the default style
# (web.md §6). `fal_factory` (T026) when FAL_KEY is set; else None.
type RendererFactory = Callable[[Screenplay, Extraction], RecordingRenderer]

RENDER_FAILED = "The renderer failed on this frame."
WIDTH, HEIGHT = 1280, 720  # the storyboard's 16:9 frame (storyboard.md §6, build_storyboard)


async def run_attempt(
    job_id: uuid.UUID,
    project_id: uuid.UUID,
    shot: tuple[int, int],
    attempt: int,
    *,
    sessions: async_sessionmaker[AsyncSession],
    model: NebiusChatModel,
    factory: RendererFactory,
    withholding: frozenset[Check] | None = None,
) -> None:
    """Attempt `attempt` alone, under `job_id`. The job ends DONE (progress 100) whatever the
    audit says; any exception fails the frame (`render`) and the job. Never raises."""
    writer = FrameWriter(sessions, project_id, job_id)
    try:
        async with sessions() as session:
            project = await session.get(ProjectRow, project_id)
        if project is None or None in (project.screenplay, project.extraction, project.plan):
            raise LookupError("the project or its stage columns are gone")
        screenplay = load_screenplay(project.screenplay)
        extraction = load_extraction(project.extraction)
        plan = load_plan(project.plan)
        found = next(s for s in plan.shots if (s.scene_index, s.number) == shot)
        renderer = factory(screenplay, extraction)
        hooks_log, on_state = frame_hooks(writer, renderer, shot)
        await render_until_accepted(
            model,
            renderer,
            found,
            screenplay,
            extraction,
            width=WIDTH,
            height=HEIGHT,
            first_attempt=attempt,
            max_renders=1,
            withholding=withholding,
            log=hooks_log,
            on_state=on_state,
        )
    except Exception:
        log.exception("frame %s attempt %d of project %s failed", shot, attempt, project_id)
        # The loop fails the frame itself on a renderer error; anything before the loop has no
        # loop to do it, so do it here too (idempotent): never leave a frame rendering.
        try:
            await writer.on_frame(shot, FrameState.FAILED, attempt, None)
        except Exception:
            log.exception("frame %s could not be marked failed", shot)
        await fail_job(sessions, job_id, RENDER_FAILED, Stage.RENDERING)
        return
    try:
        async with sessions() as session, session.begin():
            await session.execute(
                update(JobRow).where(JobRow.id == job_id).values(state=JobState.DONE, progress=100)
            )
    except Exception:
        # The frame has settled; the job stays RUNNING until the next restart sweep fails it.
        log.exception("job %s: could not record that it finished", job_id)
