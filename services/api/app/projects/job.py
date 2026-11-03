"""The upload's job: run the pipeline and write what it reports (web.md §3, §4.1, §6; T046).

Each stage's column and the job's advance are one transaction, so a page never sees a stage's
result without the job saying it is there, nor the other way round. A failure the user can act
on carries §4.1's copy (`PipelineError`); anything else is a bug: logged with its traceback, and
the job says only "something went wrong on our side". `run_job` never raises (it runs as a
background task); a cancelled one stays RUNNING for the next start's sweep.
"""

import logging
import uuid
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.frames.writer import FrameWriter
from app.grounding import Extraction
from app.jobs import JobRow, JobState
from app.llm import NebiusChatModel
from app.projects.codec import dump_extraction, dump_plan, dump_screenplay
from app.projects.model import ProjectRow
from app.projects.pipeline import (
    UNEXPECTED,
    PipelineError,
    PipelineResult,
    Stage,
    StageResult,
    run_pipeline,
)
from app.script import Screenplay
from app.storage import AssetStore
from app.storyboard.build import build_storyboard
from app.storyboard.model import StoryboardError
from app.storyboard.render import RENDER_STAGE_FAILED, RenderRecorder
from app.verify.loop import MAX_RENDERS
from app.verify.model import Check

if TYPE_CHECKING:  # attempt.py imports fail_job from here: the type only, never the module
    from app.frames.attempt import RendererFactory

log = logging.getLogger(__name__)


def _column(finished: StageResult | None) -> tuple[str | None, dict[str, Any] | None]:
    """The stage column a finished stage's result goes in (web.md §6's on_advance table)."""
    if isinstance(finished, Screenplay):
        return "screenplay", dump_screenplay(finished)
    if isinstance(finished, Extraction):
        return "extraction", dump_extraction(finished)
    return None, None


async def advance(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    project_id: uuid.UUID,
    stage: Stage,
    progress: int,
    column: str | None,
    value: dict[str, Any] | None,
    state: JobState = JobState.RUNNING,
) -> None:
    """One step: the stage's column (if any) and the job's state, stage and progress. The caller
    holds the transaction."""
    if column is not None:
        await session.execute(
            update(ProjectRow).where(ProjectRow.id == project_id).values({column: value})
        )
    await session.execute(
        update(JobRow)
        .where(JobRow.id == job_id)
        .values(state=state, stage=stage, progress=progress)
    )


async def fail_job(
    sessions: async_sessionmaker[AsyncSession], job_id: uuid.UUID, error: str, stage: Stage | None
) -> None:
    values: dict[str, Any] = {"state": JobState.FAILED, "error": error}
    if stage is not None:
        values["stage"] = stage
    try:
        async with sessions() as session, session.begin():
            await session.execute(update(JobRow).where(JobRow.id == job_id).values(values))
    except Exception:
        log.exception("job %s: could not record its failure", job_id)


async def run_job(
    job_id: uuid.UUID,
    *,
    sessions: async_sessionmaker[AsyncSession],
    store: AssetStore,
    model: NebiusChatModel,
    factory: RendererFactory | None = None,
    concurrency: int = 2,
    max_renders: int = MAX_RENDERS,
    withholding: frozenset[Check] | None = None,
) -> None:
    """With a renderer factory, the RENDERING stage follows planning (storyboard.md §4, §3.5):
    every frame through verify's loop, `concurrency` at once (FAL_CONCURRENCY), progress 60 to
    100. Without one, the job ends at planning."""
    try:
        async with sessions() as session:
            job = await session.get(JobRow, job_id)
            project = await session.get(ProjectRow, job.project_id) if job else None
        if job is None or project is None:
            raise LookupError(f"job {job_id} or its project is gone")
        project_id = project.id
        pdf = await store.get(project.pdf_path)

        async def on_advance(stage: Stage, progress: int, finished: StageResult | None) -> None:
            column, value = _column(finished)
            async with sessions() as session, session.begin():
                await advance(
                    session,
                    job_id=job_id,
                    project_id=project_id,
                    stage=stage,
                    progress=progress,
                    column=column,
                    value=value,
                )

        result = await run_pipeline(pdf, model, on_advance=on_advance)
        async with sessions() as session, session.begin():
            await advance(
                session,
                job_id=job_id,
                project_id=project_id,
                stage=Stage.PLANNING if factory is None else Stage.RENDERING,
                progress=60,
                column="plan",
                value=dump_plan(result.plan),
                state=JobState.DONE if factory is None else JobState.RUNNING,
            )
        if factory is None:
            return
        try:
            await _render(
                job_id,
                project_id,
                result,
                sessions=sessions,
                model=model,
                factory=factory,
                concurrency=concurrency,
                max_renders=max_renders,
                withholding=withholding,
            )
        except StoryboardError:  # the renderer looks down (storyboard.md §4); logged per frame
            await fail_job(sessions, job_id, RENDER_STAGE_FAILED, Stage.RENDERING)
    except PipelineError as error:
        await fail_job(sessions, job_id, error.message, error.stage)
    except Exception:
        log.exception("job %s failed unexpectedly", job_id)
        await fail_job(sessions, job_id, UNEXPECTED, None)


async def _render(
    job_id: uuid.UUID,
    project_id: uuid.UUID,
    result: PipelineResult,
    *,
    sessions: async_sessionmaker[AsyncSession],
    model: NebiusChatModel,
    factory: RendererFactory,
    concurrency: int,
    max_renders: int,
    withholding: frozenset[Check] | None,
) -> None:
    """The RENDERING stage: the storyboard through T021's writer, the job's progress mapped into
    60-100 as frames settle, DONE at 100. A StoryboardError propagates to run_job."""
    renderer = cast(RenderRecorder, factory(result.screenplay, result.extraction))
    writer = FrameWriter(sessions, project_id, job_id)

    async def progress(settled: int, total: int) -> None:
        async with sessions() as session, session.begin():
            await session.execute(
                update(JobRow)
                .where(JobRow.id == job_id)
                # GREATEST: shots settle concurrently, so writes can land out of order
                .values(
                    progress=func.greatest(
                        JobRow.progress, 60 + round(40 * settled / max(total, 1))
                    )
                )
            )

    await build_storyboard(
        model,
        renderer,
        result.plan,
        result.screenplay,
        result.extraction,
        writer=writer,
        progress=progress,
        concurrency=concurrency,
        max_renders=max_renders,
        withholding=withholding,
    )
    async with sessions() as session, session.begin():
        await session.execute(
            update(JobRow).where(JobRow.id == job_id).values(state=JobState.DONE, progress=100)
        )
