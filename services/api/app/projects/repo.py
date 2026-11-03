"""Project queries (web.md §6 *API internals*). Functions take a session and never commit."""

import uuid

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import FrameCounts, Job, ProjectSummary
from app.frames.model import FrameRow
from app.jobs.model import JobKind, JobRow, JobState
from app.projects.model import ProjectRow

# web.md §3: settled = passed + warned + withheld + failed; active = rendering + auditing.
_SETTLED = ("passed", "warned", "withheld", "failed")
_ACTIVE = ("rendering", "auditing")


async def create_upload(
    session: AsyncSession, *, project_id: uuid.UUID, owner: uuid.UUID, title: str, pdf_path: str
) -> tuple[ProjectRow, JobRow]:
    """The project and its storyboard job, QUEUED (web.md §4.1). T046 runs the job."""
    project = ProjectRow(id=project_id, owner=owner, title=title, pdf_path=pdf_path)
    job = JobRow(
        id=uuid.uuid4(), project_id=project_id, kind=JobKind.STORYBOARD, state=JobState.QUEUED
    )
    session.add(project)
    await session.flush()  # the project first: the job's foreign key needs it
    session.add(job)
    await session.flush()
    await session.refresh(project)
    await session.refresh(job)
    return project, job


async def list_summaries(session: AsyncSession, owner: uuid.UUID) -> list[ProjectSummary]:
    """The owner's projects, newest first, each with its latest job (web.md §6)."""
    return [made for _, made in await _summaries(session, owner)]


async def get_project(
    session: AsyncSession, owner: uuid.UUID, project_id: uuid.UUID
) -> tuple[ProjectRow, ProjectSummary] | None:
    """One of the owner's projects, with the same summary the list shows; None for anyone else's
    or a missing one (the route answers both with the same 404)."""
    found = await _summaries(session, owner, project_id)
    return found[0] if found else None


async def _summaries(
    session: AsyncSession, owner: uuid.UUID, project_id: uuid.UUID | None = None
) -> list[tuple[ProjectRow, ProjectSummary]]:
    """The one summary query, shared by the list and a single project (web.md §6). `pages`,
    `scenes` and `shots` are counted in SQL from the stage columns, so the list never loads a
    whole screenplay; null until their stage has run. Frame counts come from `frames` rows;
    `frames` is null with no plan or no rows, and its `total` is the plan's shot count."""
    pages = ProjectRow.screenplay["page_count"].as_integer()
    scenes = func.jsonb_array_length(ProjectRow.screenplay["scenes"])
    shots = func.jsonb_array_length(ProjectRow.plan["shots"])
    # The latest *storyboard* job: a "Try another render" (frame_attempt) never stands for the
    # project, so a failed re-render can't make a read script look failed (web.md §6, T021).
    latest = (
        select(JobRow)
        .where(JobRow.kind == JobKind.STORYBOARD)
        .ext(distinct_on(JobRow.project_id))
        .order_by(JobRow.project_id, JobRow.created_at.desc(), JobRow.id.desc())
        .subquery()
    )

    def count(states: tuple[str, ...]) -> ColumnElement[int]:
        return func.count().filter(FrameRow.state.in_(states))

    frames = (
        select(
            FrameRow.project_id,
            func.count().label("rows"),
            count(_SETTLED).label("settled"),
            count(("withheld",)).label("withheld"),
            count(_ACTIVE).label("active"),
        )
        .group_by(FrameRow.project_id)
        .subquery()
    )
    query = (
        select(
            ProjectRow,
            JobRow,
            pages,
            scenes,
            shots,
            frames.c.rows,
            frames.c.settled,
            frames.c.withheld,
            frames.c.active,
        )
        .join(latest, latest.c.project_id == ProjectRow.id)
        .join(JobRow, JobRow.id == latest.c.id)
        .outerjoin(frames, frames.c.project_id == ProjectRow.id)
        .where(ProjectRow.owner == owner)
        .order_by(ProjectRow.created_at.desc(), ProjectRow.id.desc())
    )
    if project_id is not None:
        query = query.where(ProjectRow.id == project_id)
    out: list[tuple[ProjectRow, ProjectSummary]] = []
    for project, job, p, sc, sh, rows, settled, withheld, active in await session.execute(query):
        counts = (
            FrameCounts(settled=settled, total=sh, withheld=withheld, active=active)
            if sh is not None and rows
            else None
        )
        out.append((project, summary(project, job, pages=p, scenes=sc, shots=sh, frames=counts)))
    return out


def summary(
    project: ProjectRow,
    job: JobRow,
    *,
    pages: int | None = None,
    scenes: int | None = None,
    shots: int | None = None,
    frames: FrameCounts | None = None,
) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        title=project.title,
        created_at=project.created_at,
        pages=pages,
        scenes=scenes,
        shots=shots,
        frames=frames,
        # Validated from the row's text: the database's CHECK and Job's Literal agree (web.md §6).
        job=Job.model_validate(
            {
                "id": job.id,
                "state": job.state,
                "stage": job.stage,
                "progress": job.progress,
                "error": job.error,
                "updated_at": job.updated_at,
            }
        ),
    )
