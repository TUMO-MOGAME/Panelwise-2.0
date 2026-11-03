"""T026: the storyboard job's RENDERING stage (storyboard.md §3.5, §4; web.md §4.1). The upload's
job with the fal.ai renderer over a scripted fal.ai, a scripted audit, an in-memory store and a
real Postgres; and frame_of, pure."""

import asyncio
import logging
import uuid
from dataclasses import replace
from typing import Any

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.frames.model import FrameAuditRow, FrameRow
from app.frames.writer import FrameWriter
from app.jobs import JobRow
from app.llm import Usage
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.job import run_job
from app.projects.model import ProjectRow
from app.projects.pipeline import UNEXPECTED
from app.shots import Shot
from app.storyboard.build import build_storyboard, frame_of
from app.storyboard.fal import FalRenderer
from app.storyboard.model import StoryboardError
from app.storyboard.render import RENDER_STAGE_FAILED
from app.verify import loop
from app.verify.model import (
    Audit,
    Check,
    CheckResult,
    FrameOutcome,
    FrameState,
    RenderedFrame,
    Severity,
    Verdict,
)
from tests.api.test_read import project
from tests.fakes import MemoryStore
from tests.frames.test_t021 import audit
from tests.projects.test_pipeline import Models, make
from tests.storyboard.conftest import STYLE
from tests.storyboard.test_fal import Fal

type Key = tuple[int, int]


class Script:
    """The audit: each shot's next scripted verdict (PASS when none is left)."""

    def __init__(self) -> None:
        self.verdicts: dict[Key, list[Verdict]] = {}
        self.calls: list[Key] = []
        self.broken = False
        self.delay = 0.0  # seconds each audit takes


@pytest.fixture
def scripted(monkeypatch: pytest.MonkeyPatch) -> Script:
    script = Script()

    async def fake(
        model: Any, frame: RenderedFrame, shot: Shot, screenplay: Any, extraction: Any
    ) -> Audit:
        if script.broken:
            raise RuntimeError("the database went away mid-audit")
        script.calls.append(frame.shot)
        await asyncio.sleep(script.delay)
        queue = script.verdicts.get(frame.shot, [])
        verdict = queue.pop(0) if queue else Verdict.PASS
        failed = (Check.UNSCRIPTED_PERSON,) if verdict is Verdict.FAIL else ()
        return replace(audit(frame.attempt, verdict, *failed), shot=frame.shot, seed=frame.seed)

    monkeypatch.setattr(loop, "audit_frame", fake)
    return script


async def upload_and_run(
    sessions: async_sessionmaker[AsyncSession], fal: Fal, store: MemoryStore
) -> tuple[uuid.UUID, JobRow]:
    pid, jid = await project(sessions, store, run=False)
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(fal))

    def factory(screenplay: Any, extraction: Any) -> FalRenderer:
        return FalRenderer(
            style=STYLE, store=store, screenplay=screenplay, extraction=extraction,
            client=client, key="k",
        )  # fmt: skip

    await run_job(jid, sessions=sessions, store=store, model=make(Models()), factory=factory)
    async with sessions() as s:
        job = await s.get(JobRow, jid)
    assert job is not None
    return pid, job


async def rows(sessions: async_sessionmaker[AsyncSession], pid: uuid.UUID) -> list[FrameRow]:
    async with sessions() as s:
        return list(
            await s.scalars(
                select(FrameRow)
                .where(FrameRow.project_id == pid)
                .order_by(FrameRow.scene_index, FrameRow.shot_number)
            )
        )


@pytest.mark.db
async def test_the_upload_renders_every_shot_and_ends_done_at_100(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    store, fal = MemoryStore(), Fal()
    pid, _ = await project(sessions, MemoryStore(), run=True)  # to learn the fixture's plan
    async with sessions() as s:
        plan = load_plan((await s.get(ProjectRow, pid)).plan)  # type: ignore[union-attr]
    first = (plan.shots[0].scene_index, plan.shots[0].number)
    scripted.verdicts[first] = [Verdict.FAIL, Verdict.FAIL, Verdict.FAIL]

    pid, job = await upload_and_run(sessions, fal, store)

    assert (job.state, job.stage, job.progress, job.error) == ("done", "rendering", 100, None)
    frames = await rows(sessions, pid)
    assert [((f.scene_index, f.shot_number), f.state) for f in frames] == [
        (first, "withheld"),
        *(((s.scene_index, s.number), "passed") for s in plan.shots[1:]),
    ]
    for f in frames:  # an accepted frame's image is in the store; a withheld one has none
        assert (f.asset in store.objects) if f.state == "passed" else f.asset is None
    async with sessions() as s:
        audits = list(await s.scalars(select(FrameAuditRow).where(FrameAuditRow.project_id == pid)))
    assert {a.target for a in audits} == {"storyboard"} and len(audits) == len(plan.shots) + 2
    assert len(fal.posts) == len(plan.shots) + 2  # one drawing per attempt


@pytest.mark.db
async def test_a_failed_frame_leaves_the_storyboard_going(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    # T066: one renderer error fails its own frame; the others are drawn and the job is done.
    store, fal = MemoryStore(), Fal()
    fal.statuses = [401]  # fal.ai refuses the first drawing only
    pid, job = await upload_and_run(sessions, fal, store)
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
    assert row is not None and row.plan is not None
    plan = load_plan(row.plan)
    assert (job.state, job.stage, job.progress, job.error) == ("done", "rendering", 100, None)
    frames = await rows(sessions, pid)
    assert len(frames) == len(plan.shots)
    failed = [(f.state, f.failure) for f in frames if f.state == "failed"]
    assert failed == [("failed", "render")]
    assert sum(f.state == "passed" for f in frames) == len(plan.shots) - 1


@pytest.mark.db
async def test_a_renderer_that_fails_every_frame_stops_after_three(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    store, fal = MemoryStore(), Fal()
    fal.statuses = [401] * 50  # a refused key: every drawing fails
    pid, job = await upload_and_run(sessions, fal, store)
    assert (job.state, job.stage, job.error) == ("failed", "rendering", RENDER_STAGE_FAILED)
    frames = await rows(sessions, pid)
    # min(3, shots) failed with nothing drawn: no new shot started after the third; the ones in
    # flight (2 at once) were awaited, so at most one more row exists.
    assert all(f.state == "failed" for f in frames)
    assert 3 <= len(frames) <= 4
    assert scripted.calls == []  # no drawing, so no audit


@pytest.mark.db
async def test_after_a_renderer_failure_no_new_shot_starts(
    sessions: async_sessionmaker[AsyncSession], scripted: Script, caplog: pytest.LogCaptureFixture
) -> None:
    store, fal = MemoryStore(), Fal()
    pid, jid = await project(sessions, store, run=True)
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
    assert row is not None and row.plan and row.screenplay and row.extraction
    plan = load_plan(row.plan)
    screenplay, extraction = load_screenplay(row.screenplay), load_extraction(row.extraction)
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(fal))
    renderer = FalRenderer(
        style=STYLE,
        store=store,
        screenplay=screenplay,
        extraction=extraction,
        client=client,
        key="k",
    )
    fal.statuses = [401] * 3  # the first three drawings fail: the renderer looks down
    caplog.set_level(logging.WARNING, logger="app.storyboard.build")
    with pytest.raises(StoryboardError) as failed:
        await build_storyboard(
            make(Models()), renderer, plan, screenplay, extraction,
            writer=FrameWriter(sessions, pid, jid), concurrency=1,
        )  # fmt: skip
    assert failed.value.shot == (plan.shots[0].scene_index, plan.shots[0].number)
    # One shot at a time: three failed, then nothing else started.
    assert len(fal.posts) == 3 and scripted.calls == []
    assert [f.state for f in await rows(sessions, pid)] == ["failed"] * 3
    # Never silent (storyboard.md §3.5): the renderer's own message is logged with each shot.
    lines = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(lines) == 3 and all("answered 401 for fal-ai/flux/schnell" in x for x in lines)
    assert str(failed.value.shot) in lines[0]


@pytest.mark.db
async def test_once_a_frame_is_drawn_failures_are_taken_one_frame_at_a_time(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    store, fal = MemoryStore(), Fal()
    pid, jid = await project(sessions, store, run=True)
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
    assert row is not None and row.plan and row.screenplay and row.extraction
    plan = load_plan(row.plan)
    screenplay, extraction = load_screenplay(row.screenplay), load_extraction(row.extraction)
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(fal))
    renderer = FalRenderer(
        style=STYLE, store=store, screenplay=screenplay, extraction=extraction,
        client=client, key="k",
    )  # fmt: skip
    fal.statuses = [200, *[401] * len(plan.shots)]  # one drawn, then every other refused
    board = await build_storyboard(
        make(Models()), renderer, plan, screenplay, extraction,
        writer=FrameWriter(sessions, pid, jid), concurrency=1,
    )  # fmt: skip
    states = [f.state for f in board.frames]
    # Not "down": a frame was drawn first, so every other shot was still tried, each failing alone.
    assert states == [FrameState.PASSED] + [FrameState.FAILED] * (len(plan.shots) - 1)
    failed = [f for f in board.frames if f.state is FrameState.FAILED]
    assert all(f.failure == "render" and f.asset is None for f in failed)


@pytest.mark.db
async def test_a_frame_still_in_its_audit_counts_as_drawn(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    # Review of T066: the first shot draws and sits in a slow audit while the next three fail.
    # A drawing exists, so the renderer isn't down: the storyboard goes on and the job is done.
    store, fal = MemoryStore(), Fal()
    pid, jid = await project(sessions, store, run=True)
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
    assert row is not None and row.plan and row.screenplay and row.extraction
    plan = load_plan(row.plan)
    first = plan.shots[0]
    plan = replace(plan, shots=tuple(replace(first, number=n) for n in range(1, 6)))
    screenplay, extraction = load_screenplay(row.screenplay), load_extraction(row.extraction)

    async def refusals_take_a_moment(request: httpx2.Request) -> httpx2.Response:
        # A refusal comes back over the network too: without this, three instant 401s could land
        # before the first frame's fetch and store reach its audit (main's CI, 2026-10-11).
        response = fal(request)
        if response.status_code >= 400:
            await asyncio.sleep(0.2)
        return response

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(refusals_take_a_moment))
    renderer = FalRenderer(
        style=STYLE, store=store, screenplay=screenplay, extraction=extraction,
        client=client, key="k",
    )  # fmt: skip
    fal.statuses = [200, 401, 401, 401, 401]
    scripted.delay = 1.0  # the first frame is still in its audit while the others fail
    board = await build_storyboard(
        make(Models()), renderer, plan, screenplay, extraction,
        writer=FrameWriter(sessions, pid, jid), concurrency=2,
    )  # fmt: skip
    states = [f.state for f in board.frames]
    assert states == [FrameState.PASSED] + [FrameState.FAILED] * 4


@pytest.mark.db
async def test_a_one_shot_plan_whose_frame_fails_stops(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    store, fal = MemoryStore(), Fal()
    pid, jid = await project(sessions, store, run=True)
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
    assert row is not None and row.plan and row.screenplay and row.extraction
    plan = load_plan(row.plan)
    plan = replace(plan, shots=plan.shots[:1])
    screenplay, extraction = load_screenplay(row.screenplay), load_extraction(row.extraction)
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(fal))
    renderer = FalRenderer(
        style=STYLE, store=store, screenplay=screenplay, extraction=extraction,
        client=client, key="k",
    )  # fmt: skip
    fal.statuses = [401]
    with pytest.raises(StoryboardError):
        await build_storyboard(
            make(Models()), renderer, plan, screenplay, extraction,
            writer=FrameWriter(sessions, pid, jid), concurrency=1,
        )  # fmt: skip


@pytest.mark.db
async def test_an_audit_that_breaks_is_unexpected_never_blamed_on_the_renderer(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    scripted.broken = True
    _, job = await upload_and_run(sessions, Fal(), MemoryStore())
    assert (job.state, job.error) == ("failed", UNEXPECTED)


# --- frame_of ----------------------------------------------------------------------------------


def checked(attempt: int, verdict: Verdict, *failed: tuple[Check, Severity]) -> Audit:
    bad = dict(failed)
    checks = tuple(
        CheckResult(c, bad.get(c, Severity.HARD), c not in bad, "d") for c in reversed(Check)
    )
    return Audit(
        (0, 1), attempt, 10 + attempt, None, None, checks, verdict, {}, ("v",), Usage(1, 1, 0)
    )


def test_frame_of_names_a_withheld_frame_s_hard_checks_and_a_warned_one_s_soft_in_order() -> None:
    withheld = FrameOutcome(
        (0, 1),
        FrameState.WITHHELD,
        None,
        (
            checked(
                3,
                Verdict.FAIL,
                (Check.TEXT_IN_FRAME, Severity.HARD),
                (Check.UNSCRIPTED_PERSON, Severity.HARD),
            ),
        ),
    )  # fmt: skip
    frame = frame_of(withheld, None)
    assert frame.noted_checks == (Check.UNSCRIPTED_PERSON, Check.TEXT_IN_FRAME)
    assert (frame.asset, frame.attempts, frame.seed, frame.verdict) == (None, 1, 13, Verdict.FAIL)

    warned = FrameOutcome(
        (0, 1),
        FrameState.WARNED,
        RenderedFrame((0, 1), 1, 11, b"png", 4, 4, "the text sent"),
        (checked(1, Verdict.WARN, (Check.FRAMING, Severity.SOFT), (Check.LIGHT, Severity.SOFT)),),
    )  # fmt: skip

    class Record:
        asset = "frames/k.png"

    frame = frame_of(warned, Record())  # type: ignore[arg-type]
    assert frame.noted_checks == (Check.LIGHT, Check.FRAMING)
    assert (frame.asset, frame.prompt, frame.state) == (
        "frames/k.png",
        "the text sent",
        FrameState.WARNED,
    )


@pytest.mark.db
async def test_a_progress_write_that_fails_never_fails_a_shot(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    store, fal = MemoryStore(), Fal()
    pid, jid = await project(sessions, store, run=True)
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
    assert row is not None and row.plan and row.screenplay and row.extraction
    plan = load_plan(row.plan)
    screenplay, extraction = load_screenplay(row.screenplay), load_extraction(row.extraction)
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(fal))
    renderer = FalRenderer(
        style=STYLE,
        store=store,
        screenplay=screenplay,
        extraction=extraction,
        client=client,
        key="k",
    )

    async def broken(settled: int, total: int) -> None:
        raise RuntimeError("the database blinked")

    board = await build_storyboard(
        make(Models()), renderer, plan, screenplay, extraction,
        writer=FrameWriter(sessions, pid, jid), progress=broken, concurrency=4,
    )  # fmt: skip
    assert [f.state for f in board.frames] == [FrameState.PASSED] * len(plan.shots)
    assert (board.renders, board.cached) == (len(plan.shots), 0)
