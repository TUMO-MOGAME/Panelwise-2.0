"""The repositories and the restart sweep (web.md §6 *API internals*, §4.1; T009)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.jobs import RESTARTED, JobKind, JobRow, JobState, fail_interrupted
from app.projects.pipeline import Stage
from app.projects.repo import create_upload, list_summaries

pytestmark = pytest.mark.db


async def upload(s: AsyncSession, owner: uuid.UUID, title: str) -> uuid.UUID:
    pid = uuid.uuid4()
    await create_upload(
        s, project_id=pid, owner=owner, title=title, pdf_path=f"scripts/{owner}/{pid}.pdf"
    )
    return pid


async def test_an_upload_is_a_project_and_a_queued_storyboard_job(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    owner, pid = uuid.uuid4(), uuid.uuid4()
    async with sessions() as s:
        project, job = await create_upload(
            s,
            project_id=pid,
            owner=owner,
            title="The Red Kite",
            pdf_path=f"scripts/{owner}/{pid}.pdf",
        )
        await s.commit()
    assert (project.id, project.owner, project.title) == (pid, owner, "The Red Kite")
    assert (project.screenplay, project.extraction, project.plan) == (None, None, None)
    assert (job.project_id, job.kind, job.state, job.stage, job.progress, job.error) == (
        pid,
        JobKind.STORYBOARD,
        JobState.QUEUED,
        None,
        0,
        None,
    )


async def test_the_list_is_the_owners_newest_first_with_the_latest_job(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    me, someone = uuid.uuid4(), uuid.uuid4()
    async with sessions() as s:
        first = await upload(s, me, "First")
        await upload(s, someone, "Theirs")
        second = await upload(s, me, "Second")
        # A later storyboard job on the first project is the one its summary shows (a
        # frame_attempt never is: tests/frames/test_t021.py).
        later = JobRow(
            id=uuid.uuid4(),
            project_id=first,
            kind=JobKind.STORYBOARD,
            state=JobState.RUNNING,
            progress=70,
        )
        s.add(later)
        await s.commit()
    async with sessions() as s:
        summaries = await list_summaries(s, me)
    assert [p.id for p in summaries] == [second, first]
    assert [p.title for p in summaries] == ["Second", "First"]
    assert summaries[1].job.id == later.id and summaries[1].job.state == "running"
    assert all(
        (p.pages, p.scenes, p.shots, p.frames) == (None, None, None, None) for p in summaries
    )
    async with sessions() as s:
        assert await list_summaries(s, uuid.uuid4()) == []


async def test_the_sweep_fails_queued_and_running_jobs_and_keeps_the_rest(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    owner = uuid.uuid4()
    async with sessions() as s:
        pid = await upload(s, owner, "Swept")  # its storyboard job is QUEUED
        running = JobRow(
            id=uuid.uuid4(),
            project_id=pid,
            kind=JobKind.STORYBOARD,
            state=JobState.RUNNING,
            stage=Stage.EXTRACTING,
            progress=5,
        )
        done = JobRow(
            id=uuid.uuid4(),
            project_id=pid,
            kind=JobKind.STORYBOARD,
            state=JobState.DONE,
            stage=Stage.PLANNING,
            progress=60,
        )
        failed = JobRow(
            id=uuid.uuid4(),
            project_id=pid,
            kind=JobKind.STORYBOARD,
            state=JobState.FAILED,
            error="earlier",
            progress=5,
        )
        s.add_all([running, done, failed])
        await s.commit()
    async with sessions() as s:
        stamped = await s.get(JobRow, running.id)
        assert stamped is not None
        before = stamped.updated_at
    async with sessions() as s:
        assert await fail_interrupted(s) == 2
        await s.commit()
    async with sessions() as s:
        rows = {j.id: j for j in (await s.execute(select(JobRow))).scalars()}
    assert rows[running.id].state == JobState.FAILED and rows[running.id].error == RESTARTED
    assert rows[running.id].stage == Stage.EXTRACTING  # the stage it stopped in is kept
    assert rows[running.id].updated_at > before  # the sweep is a change, so it is stamped
    assert rows[done.id].state == JobState.DONE and rows[failed.id].error == "earlier"
    queued = [j for j in rows.values() if j.id not in (running.id, done.id, failed.id)]
    assert [(j.state, j.error) for j in queued] == [(JobState.FAILED, RESTARTED)]


def test_the_restart_copy_is_web_md_verbatim() -> None:
    assert RESTARTED == "The server restarted while this ran. Upload the script again."
