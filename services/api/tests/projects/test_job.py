"""run_job: the upload's queued job runs the pipeline and writes each stage with its advance in
one transaction (web.md §3, §4.1, §6; T046). Scripted models, the test Postgres, a memory store."""

import logging
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.jobs import JobRow, JobState
from app.projects import job as job_module
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.job import run_job
from app.projects.model import ProjectRow
from app.projects.pipeline import NO_HEADINGS, READ_FAILED, UNEXPECTED, Stage
from app.projects.repo import create_upload, list_summaries
from tests.fakes import MemoryStore
from tests.projects.test_pipeline import GOOD_PDF, Models, make
from tests.script.conftest import ACTION, pdf_bytes

pytestmark = pytest.mark.db


async def queued(
    sessions: async_sessionmaker[AsyncSession], store: MemoryStore, pdf: bytes
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    owner, pid = uuid.uuid4(), uuid.uuid4()
    path = f"scripts/{owner}/{pid}.pdf"
    await store.put(path, pdf, "application/pdf")
    async with sessions() as s, s.begin():
        _, job = await create_upload(s, project_id=pid, owner=owner, title="t", pdf_path=path)
    return owner, pid, job.id


async def rows(
    sessions: async_sessionmaker[AsyncSession], pid: uuid.UUID, jid: uuid.UUID
) -> tuple[ProjectRow, JobRow]:
    async with sessions() as s:
        project, job = await s.get(ProjectRow, pid), await s.get(JobRow, jid)
    assert project is not None and job is not None
    return project, job


async def test_a_good_pdf_ends_done_at_60_with_every_column(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    store = MemoryStore()
    owner, pid, jid = await queued(sessions, store, GOOD_PDF)
    await run_job(jid, sessions=sessions, store=store, model=make(Models()))
    project, job = await rows(sessions, pid, jid)
    assert (job.state, job.stage, job.progress, job.error) == (
        JobState.DONE,
        Stage.PLANNING,
        60,
        None,
    )
    screenplay = load_screenplay(project.screenplay)
    extraction = load_extraction(project.extraction)
    plan = load_plan(project.plan)
    assert len(screenplay.scenes) == 3 and extraction.entities and plan.shots
    async with sessions() as s:
        (summary,) = await list_summaries(s, owner)
    assert (summary.pages, summary.scenes, summary.shots) == (
        screenplay.page_count, len(screenplay.scenes), len(plan.shots)
    )  # fmt: skip


async def test_each_advance_writes_its_column_and_the_job_together(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MemoryStore()
    _, pid, jid = await queued(sessions, store, GOOD_PDF)
    seen: list[tuple[str | None, int, bool, bool]] = []
    original = job_module.advance

    async def watching(session: AsyncSession, *args: object, **kw: object) -> None:
        await original(session, *args, **kw)  # type: ignore[arg-type]
        project, job = await session.get(ProjectRow, pid), await session.get(JobRow, jid)
        assert project is not None and job is not None
        seen.append((job.stage, job.progress, project.screenplay is not None,
                     project.extraction is not None))  # fmt: skip

    monkeypatch.setattr(job_module, "advance", watching)
    await run_job(jid, sessions=sessions, store=store, model=make(Models()))
    assert seen == [
        ("parsing", 0, False, False),
        ("extracting", 5, True, False),
        ("planning", 40, True, True),
        ("planning", 60, True, True),  # planned: the plan column and DONE, together
    ]


async def test_a_failing_job_write_leaves_the_column_unwritten(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MemoryStore()
    _, pid, jid = await queued(sessions, store, GOOD_PDF)
    original = job_module.advance

    async def failing(session: AsyncSession, *args: object, **kw: object) -> None:
        await original(session, *args, **kw)  # type: ignore[arg-type]
        if kw.get("stage") == Stage.EXTRACTING:
            raise RuntimeError("the job write failed")

    monkeypatch.setattr(job_module, "advance", failing)
    await run_job(jid, sessions=sessions, store=store, model=make(Models()))
    project, job = await rows(sessions, pid, jid)
    assert project.screenplay is None  # rolled back with the job's advance
    assert (job.state, job.error) == (JobState.FAILED, UNEXPECTED)


async def test_a_pipeline_error_keeps_the_earlier_columns_and_says_why(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    store = MemoryStore()
    _, pid, jid = await queued(sessions, store, GOOD_PDF)
    await run_job(jid, sessions=sessions, store=store, model=make(Models(fail_plan_on="GALLERY")))
    project, job = await rows(sessions, pid, jid)
    assert (project.screenplay is not None, project.extraction is not None, project.plan) == (
        True, True, None
    )  # fmt: skip
    assert (job.state, job.stage) == (JobState.FAILED, Stage.PLANNING)
    assert job.error == READ_FAILED.format(n="2")


async def test_a_script_with_no_headings_fails_at_parsing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    store = MemoryStore()
    no_headings = pdf_bytes([[(ACTION, "Just some prose."), (ACTION, "No headings.")]])
    _, pid, jid = await queued(sessions, store, no_headings)
    await run_job(jid, sessions=sessions, store=store, model=make(Models()))
    project, job = await rows(sessions, pid, jid)
    assert (job.state, job.stage, job.error) == (JobState.FAILED, Stage.PARSING, NO_HEADINGS)
    assert project.screenplay is None


async def test_anything_unexpected_is_logged_and_never_shown(
    sessions: async_sessionmaker[AsyncSession], caplog: pytest.LogCaptureFixture
) -> None:
    store = MemoryStore()
    _, pid, jid = await queued(sessions, store, GOOD_PDF)
    store.objects.clear()  # the PDF is gone: not something the user did
    with caplog.at_level(logging.ERROR):
        await run_job(jid, sessions=sessions, store=store, model=make(Models()))  # never raises
    _, job = await rows(sessions, pid, jid)
    assert (job.state, job.error) == (JobState.FAILED, UNEXPECTED)
    assert any(r.exc_info for r in caplog.records)  # the traceback is in the log, not the row
