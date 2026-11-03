"""T062: the architecture check (verify.md §6). The sketch renderer, and `run_check` on a real
Postgres with a scripted audit: it copies the project, works only on the copy, and refuses the
wrong bucket or a project with no plan."""

import hashlib
import io
import uuid
from dataclasses import replace
from typing import Any

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.frames import check
from app.frames.check import DEV_BUCKET, CheckRefused, SketchRenderer, run_check, sketch
from app.frames.model import FrameAuditRow, FrameRow
from app.jobs import JobKind, JobRow, JobState
from app.projects.codec import load_plan
from app.projects.model import ProjectRow
from app.script import Span
from app.shots import Framing, Movement, Shot
from app.verify import loop
from app.verify.model import Audit, Check, RenderedFrame, Verdict
from tests.api.test_read import ME, project
from tests.fakes import MemoryStore
from tests.frames.test_t021 import audit
from tests.projects.test_pipeline import Models, make

SHOT = Shot(3, 4, Framing.WIDE, Movement.STATIC, (0,), (), (), None, "", Span(1, 1, 1), "")

# --- the sketch renderer -----------------------------------------------------------------------


def test_the_same_seed_is_the_same_bytes_and_another_seed_is_not() -> None:
    assert sketch(7, 640, 360) == sketch(7, 640, 360)
    assert sketch(7, 640, 360) != sketch(8, 640, 360)


@pytest.mark.parametrize(("width", "height"), [(1280, 720), (333, 501)])
def test_a_sketch_is_a_png_of_exactly_the_size_asked_for(width: int, height: int) -> None:
    image = Image.open(io.BytesIO(sketch(1, width, height)))
    assert (image.format, image.size) == ("PNG", (width, height))
    assert image.info == {}  # no text chunks, no timestamp: nothing that varies between runs


async def test_render_stores_by_content_hash_and_records_before_it_returns() -> None:
    store = MemoryStore()
    renderer = SketchRenderer(store)
    frame = await renderer.render(SHOT, 2, 42, 1280, 720)
    path = f"frames/{hashlib.sha256(frame.png).hexdigest()}.png"
    assert store.objects == {path: (frame.png, "image/png")}
    assert renderer.record((3, 4), 2).asset == path
    assert (frame.shot, frame.attempt, frame.seed, frame.width, frame.height) == (
        (3, 4),
        2,
        42,
        1280,
        720,
    )
    assert frame.png == sketch(42, 1280, 720)
    await renderer.render(SHOT, 3, 42, 1280, 720)  # the same seed: the same address, stored once
    assert renderer.record((3, 4), 3).asset == path and len(store.objects) == 1


# --- run_check -----------------------------------------------------------------------------------


@pytest.fixture
def scripted(monkeypatch: pytest.MonkeyPatch) -> list[Verdict]:
    """The audit answers each attempt with the next verdict in the list; no model is called."""
    verdicts: list[Verdict] = []

    async def fake(
        model: Any, frame: RenderedFrame, shot: Shot, screenplay: Any, extraction: Any
    ) -> Audit:
        verdict = verdicts.pop(0)
        failed = (Check.UNSCRIPTED_PERSON,) if verdict is Verdict.FAIL else ()
        return replace(audit(frame.attempt, verdict, *failed), shot=frame.shot, seed=frame.seed)

    monkeypatch.setattr(loop, "audit_frame", fake)
    return verdicts


async def snapshot(sessions: async_sessionmaker[AsyncSession], pid: uuid.UUID) -> tuple[Any, ...]:
    """Everything the check could write for one project."""
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
        assert row is not None
        jobs = (await s.scalars(select(JobRow).where(JobRow.project_id == pid))).all()
        frames = await s.scalar(select(func.count()).where(FrameRow.project_id == pid))
        audits = await s.scalar(select(func.count()).where(FrameAuditRow.project_id == pid))
    columns = (row.title, row.owner, row.pdf_path, row.screenplay, row.extraction, row.plan)
    return columns, sorted((j.id, j.kind, j.state) for j in jobs), frames, audits


async def projects(sessions: async_sessionmaker[AsyncSession]) -> int:
    async with sessions() as s:
        return await s.scalar(select(func.count()).select_from(ProjectRow)) or 0


@pytest.mark.db
async def test_the_check_runs_the_first_shots_on_a_copy_under_one_job(
    sessions: async_sessionmaker[AsyncSession], scripted: list[Verdict]
) -> None:
    store = MemoryStore()
    pid, _ = await project(sessions, store, run=True)
    before = await snapshot(sessions, pid)
    plan = load_plan(before[0][5])
    assert len(plan.shots) > 2  # so "the first two" leaves shots out
    first, second = [(s.scene_index, s.number) for s in plan.shots[:2]]
    scripted += [Verdict.FAIL, Verdict.FAIL, Verdict.FAIL, Verdict.PASS]

    copy = await run_check(sessions, store, make(Models()), pid, bucket=DEV_BUCKET, shots=2)

    assert copy != pid and not scripted  # every scripted verdict was asked for, no more
    assert await snapshot(sessions, pid) == before  # the source is untouched
    async with sessions() as s:
        row = await s.get(ProjectRow, copy)
        jobs = (await s.scalars(select(JobRow).where(JobRow.project_id == copy))).all()
        frames = (
            await s.scalars(
                select(FrameRow)
                .where(FrameRow.project_id == copy)
                .order_by(FrameRow.scene_index, FrameRow.shot_number)
            )
        ).all()
        audits = (
            await s.scalars(
                select(FrameAuditRow)
                .where(FrameAuditRow.project_id == copy)
                .order_by(
                    FrameAuditRow.scene_index, FrameAuditRow.shot_number, FrameAuditRow.attempt
                )
            )
        ).all()
    assert row is not None
    columns = before[0]
    title = f"{columns[0]} (architecture check)"
    assert (row.title, row.owner, row.pdf_path) == (title, ME, columns[2])
    assert (row.screenplay, row.extraction, row.plan) == columns[3:]

    by_kind = {j.kind: j for j in jobs}
    assert len(jobs) == 2 and by_kind[JobKind.STORYBOARD].state == JobState.DONE
    attempt_job = by_kind[JobKind.FRAME_ATTEMPT]
    assert attempt_job.state == JobState.DONE
    assert (attempt_job.progress, attempt_job.error) == (100, None)

    # The first N shots in plan order, and nothing else: withheld after three, passed at once.
    assert [((f.scene_index, f.shot_number), f.state, f.attempt) for f in frames] == [
        (first, "withheld", 3),
        (second, "passed", 1),
    ]
    assert all(f.job_id == attempt_job.id for f in frames)
    assert frames[0].withheld_check == "unscripted_person" and frames[0].asset is None
    assert [((a.scene_index, a.shot_number), a.attempt, a.verdict) for a in audits] == [
        (first, 1, "fail"),
        (first, 2, "fail"),
        (first, 3, "fail"),
        (second, 1, "pass"),
    ]
    # Every attempt's sketch is in the store at the path its audit row names.
    for a in audits:
        png, kind = store.objects[a.frame_asset]
        assert kind == "image/png"
        assert a.frame_asset == f"frames/{hashlib.sha256(png).hexdigest()}.png"
        assert png == sketch(a.seed, check.WIDTH, check.HEIGHT)
    assert frames[1].asset == audits[3].frame_asset


@pytest.mark.db
async def test_a_render_that_raises_fails_the_frame_and_the_job(
    sessions: async_sessionmaker[AsyncSession],
    scripted: list[Verdict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryStore()
    pid, _ = await project(sessions, store, run=True)

    def broken(seed: int, width: int, height: int) -> bytes:
        raise RuntimeError("the pencil broke")

    monkeypatch.setattr(check, "sketch", broken)
    model = make(Models())
    with pytest.raises(RuntimeError, match="the pencil broke"):
        await run_check(sessions, store, model, pid, bucket=DEV_BUCKET)
    async with sessions() as s:
        job = await s.scalar(select(JobRow).where(JobRow.kind == JobKind.FRAME_ATTEMPT))
        frame = await s.scalar(select(FrameRow))
    assert job is not None and job.state == JobState.FAILED and job.project_id != pid
    assert frame is not None and (frame.state, frame.failure) == ("failed", "render")


@pytest.mark.db
async def test_it_refuses_any_bucket_but_the_dev_one_and_writes_nothing(
    sessions: async_sessionmaker[AsyncSession], scripted: list[Verdict]
) -> None:
    store = MemoryStore()
    pid, _ = await project(sessions, store, run=True)
    before = await snapshot(sessions, pid)
    model = make(Models())
    with pytest.raises(CheckRefused, match="panelwise-dev"):
        await run_check(sessions, store, model, pid, bucket="panelwise")
    assert await projects(sessions) == 1 and await snapshot(sessions, pid) == before


@pytest.mark.db
async def test_it_refuses_a_project_with_no_plan_or_no_project(
    sessions: async_sessionmaker[AsyncSession], scripted: list[Verdict]
) -> None:
    store = MemoryStore()
    pid, _ = await project(sessions, store, run=False)  # uploaded, never planned
    model = make(Models())
    for target in (pid, uuid.uuid4()):
        with pytest.raises(CheckRefused, match="no plan"):
            await run_check(sessions, store, model, target, bucket=DEV_BUCKET)
    assert await projects(sessions) == 1


@pytest.mark.db
async def test_an_audit_that_raises_fails_the_frame_mid_flight_and_the_job(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MemoryStore()
    pid, _ = await project(sessions, store, run=True)

    async def broken(*_: Any) -> Audit:
        raise RuntimeError("the judge is down")

    monkeypatch.setattr(loop, "audit_frame", broken)
    model = make(Models())
    with pytest.raises(RuntimeError, match="the judge is down"):
        await run_check(sessions, store, model, pid, bucket=DEV_BUCKET)
    async with sessions() as s:
        job = await s.scalar(select(JobRow).where(JobRow.kind == JobKind.FRAME_ATTEMPT))
        frame = await s.scalar(select(FrameRow))
    assert job is not None and job.state == JobState.FAILED
    # never left "auditing": the loop only fails a frame itself on a renderer error
    assert frame is not None and (frame.state, frame.attempt) == ("failed", 1)


@pytest.mark.db
@pytest.mark.parametrize("shots", [0, -1])
async def test_it_refuses_fewer_than_one_shot(
    sessions: async_sessionmaker[AsyncSession], scripted: list[Verdict], shots: int
) -> None:
    store = MemoryStore()
    pid, _ = await project(sessions, store, run=True)
    model = make(Models())
    with pytest.raises(CheckRefused, match="at least 1"):
        await run_check(sessions, store, model, pid, bucket=DEV_BUCKET, shots=shots)
    assert await projects(sessions) == 1
