"""T064: the comic's local check (comic.md §4a). It runs only on a planned T062 copy in the dev
bucket, and makes that copy's comic with the sketch renderer."""

import uuid
from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.comic.check import COPY_SUFFIX, run_comic_check
from app.comic.rows import ComicRow
from app.frames.check import DEV_BUCKET, CheckRefused, run_check
from app.jobs import JobKind, JobRow, JobState
from app.projects.model import ProjectRow
from app.shots import Shot
from app.verify import loop
from app.verify.model import Audit, RenderedFrame, Verdict
from tests.api.test_read import project
from tests.fakes import MemoryStore
from tests.frames.test_t021 import audit
from tests.projects.test_pipeline import Models, make

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def passing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(
        model: Any, frame: RenderedFrame, shot: Shot, screenplay: Any, extraction: Any
    ) -> Audit:
        return replace(audit(frame.attempt, Verdict.PASS), shot=frame.shot, seed=frame.seed)

    monkeypatch.setattr(loop, "audit_frame", fake)


async def comic_jobs(sessions: async_sessionmaker[AsyncSession]) -> int:
    async with sessions() as s:
        found = await s.scalar(
            select(func.count()).select_from(JobRow).where(JobRow.kind == JobKind.COMIC)
        )
    return found or 0


async def test_it_makes_a_t062_copy_s_comic(sessions: async_sessionmaker[AsyncSession]) -> None:
    store = MemoryStore()
    source, _ = await project(sessions, store, run=True)
    copy = await run_check(sessions, store, make(Models()), source, bucket=DEV_BUCKET, shots=1)
    job_id = await run_comic_check(sessions, store, make(Models()), copy, bucket=DEV_BUCKET)
    async with sessions() as s:
        job = await s.get(JobRow, job_id)
        made = await s.get(ComicRow, copy)
        mine = await s.get(ProjectRow, copy)
        theirs = await s.get(ComicRow, source)
    assert job is not None and (job.project_id, job.state) == (copy, "done")
    assert made is not None and made.job_id == job_id
    assert mine is not None and mine.title.endswith(COPY_SUFFIX)
    assert theirs is None  # the original never gets one


async def test_it_refuses_the_wrong_bucket_a_real_project_and_an_unplanned_copy(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    store = MemoryStore()
    real, _ = await project(sessions, store, run=True)
    copy = await run_check(sessions, store, make(Models()), real, bucket=DEV_BUCKET, shots=1)
    unplanned, _ = await project(sessions, store, run=False)
    async with sessions() as s, s.begin():
        row = await s.get(ProjectRow, unplanned)
        assert row is not None
        row.title += COPY_SUFFIX
    model = make(Models())
    with pytest.raises(CheckRefused, match="panelwise-dev"):
        await run_comic_check(sessions, store, model, copy, bucket="panelwise")
    for target in (real, uuid.uuid4()):
        with pytest.raises(CheckRefused, match="architecture-check copy"):
            await run_comic_check(sessions, store, model, target, bucket=DEV_BUCKET)
    with pytest.raises(CheckRefused, match="no plan"):
        await run_comic_check(sessions, store, model, unplanned, bucket=DEV_BUCKET)
    assert await comic_jobs(sessions) == 0
    async with sessions() as s, s.begin():  # a comic already being made for the copy
        s.add(JobRow(id=uuid.uuid4(), project_id=copy, kind=JobKind.COMIC, state=JobState.RUNNING))
    with pytest.raises(CheckRefused, match="comic_running"):
        await run_comic_check(sessions, store, model, copy, bucket=DEV_BUCKET)
    assert await comic_jobs(sessions) == 1
