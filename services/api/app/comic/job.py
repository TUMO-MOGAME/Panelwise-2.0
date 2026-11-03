"""The comic job (comic.md §4a; T064): render every panel at its rect through the audited loop,
letter the pages, store them by content and record the one comic of a project.

`start_comic` makes the checks and the job inside the route's transaction; `run_comic_job` runs it
in the background, like the upload's job, and always leaves the job settled. A panel the audit
already accepted for this project's comic, at its size, is reused: no render, no audit.
"""

import asyncio
import hashlib
import io
import logging
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from PIL import Image
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.comic.bubbles import place_lettering
from app.comic.layout import layout_geometry
from app.comic.model import ComicBook, ComicError, PanelFrame
from app.comic.render import failed_panel, panel_frame, render_pages, to_json, to_pdf
from app.comic.rows import ComicRow
from app.frames.attempt import RendererFactory
from app.frames.model import AuditTarget, FrameAuditRow
from app.frames.writer import FrameWriter
from app.jobs import JobKind, JobRow, JobState
from app.llm import NebiusChatModel
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.model import ProjectRow
from app.projects.pipeline import Stage
from app.script import Screenplay
from app.shots import Shot
from app.storage import AssetStore
from app.verify.loop import MAX_RENDERS, render_until_accepted
from app.verify.model import Audit, Check, FrameState, HeadSeen, Position, RecordingRenderer

log = logging.getLogger(__name__)

# comic.md §4a, verbatim: what a failed comic job says (the web shows it as written).
# T067: the renderer looks down (§4a Failure).
COMIC_RENDERER_DOWN = "No panel could be drawn, so the comic stopped. Try again in a few minutes."
COMIC_RENDER_FAILED = "A panel couldn't be drawn, so the comic stopped."  # a wrong-size PNG
DOWN_AFTER = 3  # renderer failures with no panel drawn that mean it is down
COMIC_LAYOUT_FAILED = "Shot {shot_id}'s lettering didn't fit its panel, so the comic stopped."
COMIC_LAYOUT_FAILED_ANY = "The lettering didn't fit the panels, so the comic stopped."
COMIC_UNEXPECTED = "Something went wrong on our side while making the comic. Make it again."
COMIC_RESTARTED = "The server restarted while the comic was being made. Make it again."

PANELS_SHARE = 90  # progress after the last panel; 100 comes with the stored comic

type Key = tuple[int, int]
type RefusalCode = Literal[
    "not_found",
    "not_ready",
    "comic_running",
    "llm_budget_spent",
    "image_budget_spent",
    "renderer_unavailable",
    "storage_unavailable",
]


class ComicRefused(RuntimeError):
    """A comic can't be started; `code` is the API's error code (comic.md §4a, in order)."""

    def __init__(self, code: RefusalCode) -> None:
        super().__init__(code)
        self.code: RefusalCode = code


class _RendererDown(RuntimeError):
    """No panel drawn in this job and min(3, panels to render) renderer failures (§4a, T067)."""


class _RenderFailed(RuntimeError):
    """The renderer raised on a panel, or drew it at the wrong size."""


async def start_comic(
    session: AsyncSession,
    project_id: uuid.UUID,
    owner: uuid.UUID,
    *,
    renderer: bool,
    store: bool,
    budget_spent: bool = False,
    images_spent: bool = False,
) -> JobRow:
    """§4a's checks in order, then the RUNNING comic job, in the caller's transaction. The owner's
    project is locked, so two clicks make one job. Raises before writing anything."""
    project = await session.scalar(
        select(ProjectRow)
        .where(ProjectRow.id == project_id, ProjectRow.owner == owner)
        .with_for_update()
    )
    if project is None:
        raise ComicRefused("not_found")
    upload = await session.scalar(
        select(JobRow)
        .where(JobRow.project_id == project_id, JobRow.kind == JobKind.STORYBOARD)
        .order_by(JobRow.created_at.desc(), JobRow.id.desc())
        .limit(1)
    )
    if project.plan is None or upload is None or upload.state != JobState.DONE:
        raise ComicRefused("not_ready")
    running = await session.scalar(
        select(func.count())
        .select_from(JobRow)
        .where(
            JobRow.project_id == project_id,
            JobRow.kind == JobKind.COMIC,
            JobRow.state.in_([JobState.QUEUED, JobState.RUNNING]),
        )
    )
    if running:
        raise ComicRefused("comic_running")
    if budget_spent:  # the hosted demo's monthly budget (limits.md §4, T069)
        raise ComicRefused("llm_budget_spent")
    if images_spent:  # the month's drawings (limits.md §4, T030)
        raise ComicRefused("image_budget_spent")
    if not renderer:
        raise ComicRefused("renderer_unavailable")
    if not store:
        raise ComicRefused("storage_unavailable")
    job = JobRow(
        id=uuid.uuid4(),
        project_id=project_id,
        kind=JobKind.COMIC,
        state=JobState.RUNNING,
        stage=Stage.RENDERING,
        progress=0,
    )
    session.add(job)
    await session.flush()
    return job


@dataclass(frozen=True)
class _Prior:
    """What earlier comic jobs logged for one panel."""

    last_attempt: int  # 0 when none
    accepted: FrameAuditRow | None  # the latest pass or warn, if any


async def _priors(
    sessions: async_sessionmaker[AsyncSession], project_id: uuid.UUID
) -> dict[Key, _Prior]:
    async with sessions() as session:
        rows = (
            await session.scalars(
                select(FrameAuditRow)
                .where(
                    FrameAuditRow.project_id == project_id,
                    FrameAuditRow.target == AuditTarget.COMIC.value,
                )
                .order_by(FrameAuditRow.attempt)
            )
        ).all()
    out: dict[Key, _Prior] = {}
    for row in rows:
        key = (row.scene_index, row.shot_number)
        before = out.get(key, _Prior(0, None))
        accepted = row if row.verdict in ("pass", "warn") else before.accepted
        out[key] = _Prior(max(before.last_attempt, row.attempt), accepted)
    return out


def _size(png: bytes) -> tuple[int, int] | None:
    try:
        with Image.open(io.BytesIO(png)) as image:
            return image.size
    except OSError, ValueError:
        return None


async def _reused(
    store: AssetStore, prior: _Prior | None, size: tuple[int, int]
) -> tuple[PanelFrame, str] | None:
    """§4a step 1: the panel's latest accepted comic attempt, if its PNG is exactly this size."""
    if prior is None or prior.accepted is None:
        return None
    row = prior.accepted
    try:
        png = await store.get(row.frame_asset)
    except Exception:
        log.warning("comic panel %s: its accepted frame can't be read", row.frame_asset)
        return None
    if _size(png) != size:
        return None
    positions = {name: Position(value) for name, value in row.positions.items()}
    heads = tuple(  # T098: the row's head boxes (T097); None before 0010 or when not asked
        HeadSeen(item["person"], item["character"], tuple(item["box"])) for item in row.heads or ()
    )
    return PanelFrame(png, positions, False, heads=heads), row.frame_asset


def _hooks(
    writer: FrameWriter, renderer: RecordingRenderer, key: Key, states: list[FrameState]
) -> tuple[Callable[[Audit], Awaitable[None]], Callable[[FrameState, int], Awaitable[None]]]:
    """Comic's own hooks (§4a step 2), never frame_hooks: a panel has no frames row. `on_state`
    only records, so a FAILED state tells the job the renderer raised."""

    async def log_audit(audit: Audit) -> None:
        await writer.log(audit, renderer.record(key, audit.attempt).asset)

    async def on_state(state: FrameState, attempt: int) -> None:
        states.append(state)

    return log_audit, on_state


async def _progress(
    sessions: async_sessionmaker[AsyncSession], job_id: uuid.UUID, value: int
) -> None:
    async with sessions() as session, session.begin():
        await session.execute(update(JobRow).where(JobRow.id == job_id).values(progress=value))


async def _fail(sessions: async_sessionmaker[AsyncSession], job_id: uuid.UUID, error: str) -> None:
    try:
        async with sessions() as session, session.begin():
            await session.execute(
                update(JobRow)
                .where(JobRow.id == job_id)
                .values(state=JobState.FAILED, error=error, stage=Stage.RENDERING)
            )
    except Exception:
        log.exception("comic job %s: could not record its failure", job_id)


def _layout_message(error: ComicError, screenplay: Screenplay | None) -> str:
    """COMIC_LAYOUT_FAILED naming the shot as the web does (web.md §6 shot_id), when the error
    names one the screenplay has; else the message that names none."""
    if error.shot is None or screenplay is None:
        return COMIC_LAYOUT_FAILED_ANY
    scene_index, number = error.shot
    if not 0 <= scene_index < len(screenplay.scenes):
        return COMIC_LAYOUT_FAILED_ANY
    return COMIC_LAYOUT_FAILED.format(shot_id=f"{screenplay.scenes[scene_index].number}.{number}")


async def _put(store: AssetStore, folder: str, data: bytes, ext: str, kind: str) -> str:
    path = f"{folder}/{hashlib.sha256(data).hexdigest()}.{ext}"
    await store.put(path, data, kind)  # a content address: put is idempotent
    return path


async def _all_or_cancel(work: list[Coroutine[Any, Any, None]]) -> None:
    """Run every panel; the first one to raise cancels the rest, which are awaited, and its error
    is raised as itself (T073), so run_comic_job's handlers see one exception, never a group."""
    tasks = [asyncio.create_task(w) for w in work]
    try:
        for done in asyncio.as_completed(tasks):
            await done
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def run_comic_job(
    job_id: uuid.UUID,
    *,
    sessions: async_sessionmaker[AsyncSession],
    store: AssetStore,
    model: NebiusChatModel,
    factory: RendererFactory,
    max_renders: int = MAX_RENDERS,
    withholding: frozenset[Check] | None = None,
    concurrency: int = 1,
) -> None:
    """comic.md §4a end to end for the job's project. Never raises: every failure is the job
    FAILED with one of §4a's messages, the cause logged. `concurrency` panels are in the
    renderer at once (T073); a refused value is the one ValueError, before anything runs."""
    if concurrency < 1:
        raise ValueError(f"concurrency is at least 1, not {concurrency}")
    screenplay: Screenplay | None = None
    try:
        async with sessions() as session:
            job = await session.get(JobRow, job_id)
            project = None if job is None else await session.get(ProjectRow, job.project_id)
        if job is None or project is None or project.plan is None:
            raise RuntimeError(f"comic job {job_id} has no planned project")
        screenplay = load_screenplay(project.screenplay)
        extraction = load_extraction(project.extraction)
        plan = load_plan(project.plan)
        shots: Mapping[Key, Shot] = {(s.scene_index, s.number): s for s in plan.shots}

        book: ComicBook = await asyncio.to_thread(layout_geometry, plan, screenplay)
        panels = [panel for page in book.pages for panel in page.panels]
        priors = await _priors(sessions, project.id)
        renderer = factory(screenplay, extraction)
        writer = FrameWriter(sessions, project.id, job_id, target=AuditTarget.COMIC)
        frames: dict[Key, PanelFrame] = {}
        paths: dict[Key, str] = {}
        reuse = {
            (p.scene_index, p.shot_number): await _reused(
                store, priors.get((p.scene_index, p.shot_number)), (p.rect[2], p.rect[3])
            )
            for p in panels
        }
        to_render = sum(found is None for found in reuse.values())
        failed = settled = 0  # this job's panels whose renderer raised / that are done
        drawn: set[Key] = set()  # panels that reached their audit: the renderer works (T067)
        gate = asyncio.Semaphore(concurrency)
        stop = asyncio.Event()  # set by a panel failing the job, before it frees its slot
        progress_lock = asyncio.Lock()

        async def settle() -> None:
            nonlocal settled
            async with progress_lock:  # one write at a time, so progress only rises (§4a step 5)
                settled += 1
                await _progress(sessions, job_id, round(PANELS_SHARE * settled / len(panels)))

        async def one(panel: Any) -> None:
            nonlocal failed
            key = (panel.scene_index, panel.shot_number)
            shot = shots[key]
            size = (panel.rect[2], panel.rect[3])
            reused = reuse[key]
            if reused is not None:
                frames[key], paths[key] = reused
                await settle()
                return
            prior = priors.get(key)
            states: list[FrameState] = []
            log_audit, record_state = _hooks(writer, renderer, key, states)

            async def on_state(state: FrameState, attempt: int) -> None:
                await record_state(state, attempt)
                if state is FrameState.AUDITING:  # counted at once, not when the panel ends
                    drawn.add(key)

            async with gate:
                if stop.is_set():  # a panel already failed the job: start nothing new
                    return
                try:
                    try:
                        outcome = await render_until_accepted(
                            model,
                            renderer,
                            shot,
                            screenplay,
                            extraction,
                            width=size[0],
                            height=size[1],
                            max_renders=max_renders,
                            withholding=withholding,
                            heads=True,  # T097: where each head is, for the bubbles (T098)
                            first_attempt=1 + (prior.last_attempt if prior else 0),
                            log=log_audit,
                            on_state=on_state,
                        )
                    except Exception as error:
                        if not states or states[-1] is not FrameState.FAILED:
                            raise
                        # §4a Failure (T067): this panel gets the failed card and the comic goes
                        # on, unless the renderer looks down.
                        log.warning(
                            "comic job %s: panel %s couldn't be drawn: %s", job_id, key, error
                        )
                        failed += 1
                        if not drawn and failed >= min(DOWN_AFTER, to_render):
                            raise _RendererDown(f"{failed} panel(s) failed, none drawn") from error
                        frames[key] = failed_panel(shot)
                        await settle()
                        return
                    # Still holding the slot: a panel that fails the job does so before another
                    # starts.
                    frames[key] = panel_frame(outcome, shot)  # ComicError if not accepted/withheld
                    if outcome.frame is not None and not frames[key].withheld:
                        size_drawn = _size(outcome.frame.png)
                        if size_drawn != size:  # §4a step 3: the renderer ignored the size
                            raise _RenderFailed(f"{key} was drawn at {size_drawn}, not {size}")
                        paths[key] = renderer.record(key, outcome.frame.attempt).asset
                except BaseException:
                    stop.set()  # whatever failed the job, before the slot is freed
                    raise
            await settle()

        await _all_or_cancel([one(panel) for panel in panels])

        lettered = await asyncio.to_thread(place_lettering, book, screenplay, plan, frames)
        pages = await asyncio.to_thread(render_pages, lettered, frames)
        pdf = await asyncio.to_thread(to_pdf, pages)
        page_paths = [await _put(store, "comics", page, "png", "image/png") for page in pages]
        pdf_path = await _put(store, "comics", pdf, "pdf", "application/pdf")
        layout = to_json(lettered, paths)

        values = {"job_id": job_id, "layout": layout, "pages": page_paths, "pdf": pdf_path,
                  "made_at": func.clock_timestamp()}  # fmt: skip
        async with sessions() as session, session.begin():
            await session.execute(
                insert(ComicRow)
                .values(project_id=project.id, **values)
                .on_conflict_do_update(index_elements=["project_id"], set_=values)
            )
            await session.execute(
                update(JobRow).where(JobRow.id == job_id).values(state=JobState.DONE, progress=100)
            )
    except _RendererDown:
        log.exception("comic job %s: the renderer looks down", job_id)
        await _fail(sessions, job_id, COMIC_RENDERER_DOWN)
    except _RenderFailed:
        log.exception("comic job %s: a panel couldn't be drawn", job_id)
        await _fail(sessions, job_id, COMIC_RENDER_FAILED)
    except ComicError as error:
        log.exception("comic job %s: %s", job_id, error)
        await _fail(sessions, job_id, _layout_message(error, screenplay))
    except Exception:
        log.exception("comic job %s failed", job_id)
        await _fail(sessions, job_id, COMIC_UNEXPECTED)
