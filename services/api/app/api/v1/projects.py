"""POST and GET /api/v1/projects: the upload and the list (web.md §4.1, §6; T053)."""

import asyncio
import logging
import re
import uuid
from pathlib import PurePath
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import ApiError
from app.api.v1.downloads import download_name, with_download
from app.api.v1.schemas import (
    ComicView,
    FrameView,
    LinesView,
    Project,
    ProjectSummary,
    ShotView,
    StoryboardPdfView,
)
from app.comic.job import ComicRefused, run_comic_job, start_comic
from app.comic.rows import ComicRow
from app.comic.views import comic_job_view, comic_view
from app.core.auth import Caller, current_caller
from app.core.config import withholding
from app.frames import ACCEPTED, FrameRow, audits_of, frame_view, frames_of
from app.frames.attempt import RendererFactory, run_attempt
from app.jobs import JobKind, JobRow, JobState
from app.limits.checks import (
    budget_spent,
    check_budget,
    check_images,
    check_pages,
    check_uploads,
    images_spent,
)
from app.llm import NebiusChatModel
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.job import fail_job, run_job
from app.projects.model import ProjectRow
from app.projects.pipeline import UNEXPECTED, Stage
from app.projects.repo import create_upload, get_project, list_summaries, summary
from app.projects.views import entity_views, lines_view, report_view, scene_views, shot_views
from app.storage import AssetStore, StorageError
from app.storyboard.document import export_pdf, frames_from_rows
from app.storyboard.styles import StyleRegistry

router = APIRouter()
log = logging.getLogger(__name__)

_FRAMING = 64 * 1024  # multipart boundaries and headers on top of the file itself
_MAX_TITLE_BYTES = 1024
_TITLE_CHARS = 200


def _store(request: Request) -> AssetStore:
    store: AssetStore | None = request.app.state.store
    if store is None:
        raise ApiError(503, "storage_unavailable")
    return store


def _title(typed: object, filename: str | None) -> str:
    text = typed if isinstance(typed, str) else ""
    if len(text.encode()) > _MAX_TITLE_BYTES:
        raise ApiError(413, "too_large")
    # The file name without .pdf (web.md §3); PurePath.stem keeps ".pdf" whole, as a dotfile.
    name = PurePath(filename or "").name
    text = text.strip() or re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE).strip()
    return text[:_TITLE_CHARS].strip() or "Untitled"


def start(request: Request, job_id: uuid.UUID) -> None:
    """Run the job as a background task in this process (web.md §4.1). Without a model it fails
    at once with the unexpected-error copy rather than sitting QUEUED until a restart."""
    state = request.app.state
    if state.model is None:
        log.error("job %s cannot run: NEBIUS_API_KEY is not set", job_id)
        work = fail_job(state.sessions, job_id, UNEXPECTED, None)
    else:
        work = run_job(
            job_id,
            sessions=state.sessions,
            store=state.store,
            model=state.model,
            factory=state.renderer_factory,
            concurrency=state.settings.fal_concurrency,
            max_renders=state.settings.render_max_attempts,
            withholding=withholding(state.settings),
        )
    task = asyncio.create_task(work)
    state.tasks.add(task)
    task.add_done_callback(state.tasks.discard)


@router.post("/projects", status_code=202)
async def upload(
    request: Request, caller: Annotated[Caller, Depends(current_caller)]
) -> JSONResponse:
    """In web.md §6's order. No UploadFile or Form parameter: FastAPI would read the whole body
    before the caller is checked. So: who (401/503), storage (503), the demo's budget and the
    day's uploads (429, T069), the declared length (411/413), then the form, the file's own size
    (413), the PDF header (400), its pages (413, T069), and only then storage."""
    settings = request.app.state.settings
    store = _store(request)
    # The hosted demo's limits (limits.md §4, T069): nothing read or stored past a refusal.
    async with request.app.state.sessions() as session:
        await check_budget(request, session)
        await check_images(request, session)  # T030: right after the token budget
        await check_uploads(request, session, caller.user_id)
    length = request.headers.get("content-length")
    if length is None or not length.isdigit():
        raise ApiError(411, "length_required")
    if int(length) > settings.upload_max_bytes + _FRAMING:
        raise ApiError(413, "too_large")
    try:
        form = await request.form(max_files=1, max_fields=1)
    except StarletteHTTPException as exc:  # Starlette's form limits, raised as 400
        raise ApiError(400, "bad_form") from exc
    file = form.get("file")
    if not isinstance(file, UploadFile):  # absent, or sent without a filename (a text field)
        raise ApiError(400, "no_file")
    if file.size is None or file.size > settings.upload_max_bytes:
        raise ApiError(413, "too_large")
    title = _title(form.get("title"), file.filename)
    data = await file.read()
    if not data.startswith(b"%PDF-"):
        raise ApiError(400, "not_a_pdf")
    await asyncio.to_thread(check_pages, request, data)

    project_id = uuid.uuid4()
    path = f"scripts/{caller.user_id}/{project_id}.pdf"
    try:
        # Storage first: a row never points at a missing file (a failed insert leaves only an
        # unreferenced one).
        await store.put(path, data, "application/pdf")
    except StorageError as exc:
        raise ApiError(503, "storage_unavailable") from exc
    async with request.app.state.sessions() as session, session.begin():
        project, job = await create_upload(
            session, project_id=project_id, owner=caller.user_id, title=title, pdf_path=path
        )
        made = summary(project, job)
    start(request, job.id)  # after the commit: the job reads what this transaction wrote
    body: dict[str, Any] = {"project": made, "job": made.job}
    return JSONResponse({k: v.model_dump(mode="json") for k, v in body.items()}, status_code=202)


@router.get("/projects")
async def list_projects(
    request: Request, caller: Annotated[Caller, Depends(current_caller)]
) -> list[ProjectSummary]:
    async with request.app.state.sessions() as session:
        return await list_summaries(session, caller.user_id)


# --- the reads (T047; web.md §6 *API internals: the reads and the frames table*) -----------

_SIGNED_URL_S = 3600  # a frame's signed image URL lives an hour


async def _owned(
    request: Request, caller: Caller, project_id: str
) -> tuple[ProjectRow, ProjectSummary]:
    """The caller's project, or 404 -- the same answer for a malformed id, a missing project and
    someone else's, so ids can't be probed. `{id}` is a str parsed here: typed UUID, FastAPI
    would answer a malformed one with its own 422."""
    try:
        pid = uuid.UUID(project_id)
    except ValueError as exc:
        raise ApiError(404, "not_found") from exc
    async with request.app.state.sessions() as session:
        found = await get_project(session, caller.user_id, pid)
    if found is None:
        raise ApiError(404, "not_found")
    return found


@router.get("/projects/{project_id}")
async def read_project(
    request: Request, project_id: str, caller: Annotated[Caller, Depends(current_caller)]
) -> Project:
    row, made = await _owned(request, caller, project_id)
    screenplay = load_screenplay(row.screenplay) if row.screenplay is not None else None
    extraction = load_extraction(row.extraction) if row.extraction is not None else None
    plan = load_plan(row.plan) if row.plan is not None else None
    return Project.model_validate(
        made.model_dump()
        | {
            "scene_list": scene_views(screenplay, plan) if screenplay else None,
            "entities": entity_views(extraction) if extraction else None,
            "report": report_view(extraction, plan) if extraction else None,
        }
    )


@router.get("/projects/{project_id}/lines")
async def read_lines(
    request: Request, project_id: str, caller: Annotated[Caller, Depends(current_caller)]
) -> LinesView:
    row, _ = await _owned(request, caller, project_id)
    if row.screenplay is None:
        raise ApiError(409, "not_ready")
    return lines_view(load_screenplay(row.screenplay))


@router.get("/projects/{project_id}/shots")
async def read_shots(
    request: Request, project_id: str, caller: Annotated[Caller, Depends(current_caller)]
) -> list[ShotView]:
    row, _ = await _owned(request, caller, project_id)
    if row.screenplay is None or row.extraction is None or row.plan is None:
        raise ApiError(409, "not_ready")
    return shot_views(
        load_screenplay(row.screenplay), load_extraction(row.extraction), load_plan(row.plan)
    )


@router.get("/projects/{project_id}/frames")
async def read_frames(
    request: Request, project_id: str, caller: Annotated[Caller, Depends(current_caller)]
) -> list[FrameView]:
    """One FrameView per `frames` row; no rows exist until T021 writes them."""
    row, _ = await _owned(request, caller, project_id)
    async with request.app.state.sessions() as session:
        frames = await frames_of(session, row.id)
        audits = await audits_of(session, row.id) if frames else {}
    if not frames:
        return []
    if row.screenplay is None:  # frames are written from a plan, which needs a screenplay
        raise ApiError(409, "not_ready")
    screenplay = load_screenplay(row.screenplay)
    store: AssetStore | None = request.app.state.store
    # T122: every accepted frame's link in one call (one at a time took 4.9 s for 21 frames)
    shown = [f for f in frames if f.state in ACCEPTED and f.asset is not None]
    urls: dict[tuple[int, int], str] = {}
    if shown:
        if store is None:
            raise ApiError(503, "storage_unavailable")
        try:
            links = await store.signed_urls([f.asset for f in shown if f.asset], _SIGNED_URL_S)
        except StorageError as exc:
            raise ApiError(503, "storage_unavailable") from exc
        urls = {(f.scene_index, f.shot_number): u for f, u in zip(shown, links, strict=True)}
    views: list[FrameView] = []
    for frame in frames:
        url = urls.get((frame.scene_index, frame.shot_number))
        attempts = audits.get((frame.scene_index, frame.shot_number), [])
        views.append(
            frame_view(
                frame,
                screenplay,
                url,
                attempts,
                max_renders=request.app.state.settings.render_max_attempts,
            )
        )
    return views


_INT4_MAX = 2**31 - 1  # frames.scene_index and shot_number are int4


def _index(text: str) -> int:
    """A path segment that must be a whole number the database's int columns can hold; anything
    else names no frame (404), never a database error."""
    if not text.isdecimal() or int(text) > _INT4_MAX:
        raise ApiError(404, "not_found")
    return int(text)


@router.post("/projects/{project_id}/frames/{scene_index}/{number}/attempts", status_code=202)
async def try_another_render(
    request: Request,
    project_id: str,
    scene_index: str,
    number: str,
    caller: Annotated[Caller, Depends(current_caller)],
) -> FrameView:
    """One more audited attempt on a withheld or failed frame (T066), in web.md §6's order: who;
    the frame, locked from its read to the commit (one attempt per frame at a time); its state
    (409); what the attempt needs (503, nothing written); then the job and the row together, and
    the work in the background."""
    project, _ = await _owned(request, caller, project_id)
    shot = (_index(scene_index), _index(number))
    state = request.app.state
    async with state.sessions() as session, session.begin():
        frame = await session.scalar(
            select(FrameRow)
            .where(
                FrameRow.project_id == project.id,
                FrameRow.scene_index == shot[0],
                FrameRow.shot_number == shot[1],
            )
            .with_for_update()
        )
        if frame is None:
            raise ApiError(404, "not_found")
        if frame.state not in ("withheld", "failed"):
            raise ApiError(409, "not_withheld")  # the code keeps its T021 name
        if (
            project.screenplay is None
            or project.plan is None
            or not any((s.scene_index, s.number) == shot for s in load_plan(project.plan).shots)
        ):
            raise ApiError(409, "not_ready")
        await check_budget(request, session)  # T069: after the 409s, before the 503s
        await check_images(request, session)  # T030
        if state.renderer_factory is None or state.model is None:
            raise ApiError(503, "renderer_unavailable")
        if state.store is None:
            raise ApiError(503, "storage_unavailable")
        job = JobRow(
            id=uuid.uuid4(),
            project_id=project.id,
            kind=JobKind.FRAME_ATTEMPT,
            state=JobState.RUNNING,
            stage=Stage.RENDERING,
            progress=60,
        )
        session.add(job)
        await session.flush()
        frame.state, frame.attempt, frame.job_id = "rendering", frame.attempt + 1, job.id
        frame.withheld_check = frame.failure = None
        attempt = frame.attempt
        view = frame_view(
            frame,
            load_screenplay(project.screenplay),
            None,
            max_renders=state.settings.render_max_attempts,
        )
    task = asyncio.create_task(
        run_attempt(
            job.id,
            project.id,
            shot,
            attempt,
            sessions=state.sessions,
            model=state.model,
            factory=state.renderer_factory,
            withholding=withholding(state.settings),
        )
    )
    state.tasks.add(task)
    task.add_done_callback(state.tasks.discard)
    return view


# --- the comic (T064; comic.md §4a, web.md §6) ------------------------------------------------

_COMIC_STATUS = {
    "not_found": 404,
    "not_ready": 409,
    "comic_running": 409,
    "llm_budget_spent": 429,
    "image_budget_spent": 429,  # T030
    "renderer_unavailable": 503,
    "storage_unavailable": 503,
}


@router.post("/projects/{project_id}/comic", status_code=202)
async def make_comic(
    request: Request, project_id: str, caller: Annotated[Caller, Depends(current_caller)]
) -> JSONResponse:
    """Start the project's comic: comic.md §4a's checks in order, nothing written before an
    answer, then the job runs in the background like the upload's."""
    try:
        pid = uuid.UUID(project_id)
    except ValueError as exc:
        raise ApiError(404, "not_found") from exc
    state = request.app.state
    factory: RendererFactory | None = state.renderer_factory
    model: NebiusChatModel | None = state.model
    store: AssetStore | None = state.store
    try:
        async with state.sessions() as session, session.begin():
            job = await start_comic(
                session,
                pid,
                caller.user_id,
                renderer=factory is not None and model is not None,
                store=store is not None,
                budget_spent=await budget_spent(request, session),
                images_spent=await images_spent(request, session),
            )
    except ComicRefused as refused:
        raise ApiError(_COMIC_STATUS[refused.code], refused.code) from refused
    if factory is None or model is None or store is None:  # start_comic refused these already
        raise ApiError(503, "renderer_unavailable")
    task = asyncio.create_task(
        run_comic_job(
            job.id,
            sessions=state.sessions,
            store=store,
            model=model,
            factory=factory,
            max_renders=state.settings.render_max_attempts,
            concurrency=state.settings.fal_concurrency,
            withholding=withholding(state.settings),
        )
    )
    state.tasks.add(task)
    task.add_done_callback(state.tasks.discard)
    return JSONResponse(
        status_code=202, content={"job": comic_job_view(job).model_dump(mode="json")}
    )


@router.get("/projects/{project_id}/storyboard/pdf")
async def storyboard_pdf(
    request: Request, project_id: str, caller: Annotated[Caller, Depends(current_caller)]
) -> StoryboardPdfView:
    """T027 (web.md §6; storyboard.md §3.4 Delivery): the PDF of a settled storyboard, built on
    demand from the frames rows and stored by its document key, as a signed URL."""
    project, made = await _owned(request, caller, project_id)
    if made.job.state != "done" or project.plan is None or project.screenplay is None:
        raise ApiError(409, "not_ready")
    state = request.app.state
    async with state.sessions() as session:
        rows = await frames_of(session, project.id)
        audits = await audits_of(session, project.id)
    plan = load_plan(project.plan)
    by_shot = {(r.scene_index, r.shot_number): r for r in rows}
    ordered = [by_shot.get((s.scene_index, s.number)) for s in plan.shots]
    if any(r is None or r.state in ("rendering", "auditing") for r in ordered):
        raise ApiError(409, "not_ready")
    store: AssetStore | None = state.store
    if store is None:
        raise ApiError(503, "storage_unavailable")
    styles: StyleRegistry | None = state.styles
    if styles is None:
        raise ApiError(503, "styles_unavailable")
    frames = frames_from_rows(
        [r for r in ordered if r is not None], [a for listed in audits.values() for a in listed]
    )
    try:
        path = await export_pdf(
            store, project.id, styles.get(None), plan, load_screenplay(project.screenplay), frames
        )
        url = await store.signed_url(path, _SIGNED_URL_S)
    except StorageError as exc:
        raise ApiError(503, "storage_unavailable") from exc
    # T126: saved under the screenplay's title, not the Storage key
    return StoryboardPdfView(pdf_url=with_download(url, download_name(project.title, "storyboard")))


@router.get("/projects/{project_id}/comic")
async def read_comic(
    request: Request, project_id: str, caller: Annotated[Caller, Depends(current_caller)]
) -> ComicView:
    """The latest comic job and the last finished comic, every page and the PDF signed."""
    project, _ = await _owned(request, caller, project_id)
    if project.plan is None:
        raise ApiError(409, "not_ready")
    state = request.app.state
    async with state.sessions() as session:
        job = await session.scalar(
            select(JobRow)
            .where(JobRow.project_id == project.id, JobRow.kind == JobKind.COMIC)
            .order_by(JobRow.created_at.desc(), JobRow.id.desc())
            .limit(1)
        )
        comic = await session.get(ComicRow, project.id)
    page_urls: list[str] = []
    pdf_url: str | None = None
    if comic is not None:
        store: AssetStore | None = state.store
        if store is None:
            raise ApiError(503, "storage_unavailable")
        try:
            # T122: the pages and the PDF in one call; the PDF's link is the last
            *page_urls, pdf_url = await store.signed_urls([*comic.pages, comic.pdf], _SIGNED_URL_S)
        except StorageError as exc:
            raise ApiError(503, "storage_unavailable") from exc
        pdf_url = with_download(pdf_url, download_name(project.title, "comic"))  # T126
    can_make = (
        state.renderer_factory is not None and state.model is not None and state.store is not None
    )
    return comic_view(project, job, comic, page_urls, pdf_url, can_make=can_make)
