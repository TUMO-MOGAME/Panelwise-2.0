"""T021: the frames writer, its hooks, the frame sweep, the audits read and "Try another render"
(verify.md §6; web.md §4.1, §6). A real Postgres, a fake renderer, a scripted audit."""

import asyncio
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.frames.model import FrameAuditRow, FrameRow
from app.frames.writer import FrameWriter, frame_hooks, withheld_check
from app.jobs import JobKind, JobRow, JobState, fail_interrupted_frames
from app.llm import Usage
from app.main import create_app
from app.projects.codec import load_plan
from app.projects.model import ProjectRow
from app.shots import Shot
from app.verify import loop
from app.verify.model import (
    Audit,
    Check,
    CheckResult,
    FrameState,
    Position,
    RenderedFrame,
    Severity,
    Verdict,
)
from tests.api.test_read import ME, SOMEONE, auth, project
from tests.fakes import FakeVerifier, MemoryStore
from tests.projects.test_pipeline import Models, make

pytestmark = pytest.mark.db


def audit(attempt: int, verdict: Verdict, *failed: Check) -> Audit:
    checks = tuple(CheckResult(c, Severity.HARD, c not in failed, "detail") for c in Check)
    return Audit(
        (0, 1), attempt, 1000 + attempt, None, None, checks, verdict,
        {"NANDI": Position.LEFT}, ("vision", "judge"), Usage(10, 5, 0),
    )  # fmt: skip


@dataclass(frozen=True)
class Record:
    asset: str


class FakeRenderer:
    """A RecordingRenderer: frames/<shot>-<attempt>.png, recorded before render returns."""

    def __init__(self, *, fail: bool = False) -> None:
        self.records: dict[tuple[tuple[int, int], int], Record] = {}
        self.fail = fail

    async def render(
        self, shot: Shot, attempt: int, seed: int, width: int, height: int
    ) -> RenderedFrame:
        if self.fail:
            raise RuntimeError("the renderer fell over")
        key = (shot.scene_index, shot.number)
        self.records[(key, attempt)] = Record(f"frames/{key[0]}-{key[1]}-{attempt}.png")
        return RenderedFrame(key, attempt, seed, b"png", width, height, "p")

    def record(self, shot: tuple[int, int], attempt: int) -> Record:
        return self.records[(shot, attempt)]


class HeldRenderer(FakeRenderer):
    """A FakeRenderer whose render waits until the test releases it, so a frame stays mid-retry
    for as long as the test needs (the retry runs in TestClient's own thread and loop)."""

    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()

    async def render(
        self, shot: Shot, attempt: int, seed: int, width: int, height: int
    ) -> RenderedFrame:
        if not await asyncio.to_thread(self.release.wait, 10):
            raise AssertionError("the test never released the renderer")
        return await super().render(shot, attempt, seed, width, height)


# --- the writer -------------------------------------------------------------------------------


async def test_every_attempt_is_a_row_and_the_seed_needs_a_bigint(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pid, jid = await project(sessions, MemoryStore(), run=False)
    writer = FrameWriter(sessions, pid, jid)
    big = audit(1, Verdict.FAIL, Check.UNSCRIPTED_PERSON)
    big = replace(big, seed=4_000_000_000)  # seed_for is unsigned 32-bit
    await writer.log(big, "frames/a.png")
    await writer.log(audit(2, Verdict.ERROR), "frames/b.png")
    async with sessions() as s:
        rows = (await s.scalars(select(FrameAuditRow).order_by(FrameAuditRow.attempt))).all()
    assert [(r.attempt, r.seed, r.verdict, r.frame_asset) for r in rows] == [
        (1, 4_000_000_000, "fail", "frames/a.png"),
        (2, 1002, "error", "frames/b.png"),
    ]
    assert rows[0].positions == {"NANDI": "left"} and rows[0].models == ["vision", "judge"]
    assert (rows[0].prompt_tokens, rows[0].completion_tokens) == (10, 5)
    assert rows[0].checks[0] == {
        "check": "unscripted_person",
        "severity": "hard",
        "ok": False,
        "detail": "detail",
    }
    with pytest.raises(IntegrityError):  # one row per attempt of a frame
        await writer.log(audit(1, Verdict.PASS), "frames/c.png")


async def test_on_frame_sets_every_column_on_every_write(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pid, jid = await project(sessions, MemoryStore(), run=False)
    writer = FrameWriter(sessions, pid, jid)

    async def row() -> FrameRow:
        async with sessions() as s:
            got = await s.get(FrameRow, (pid, 0, 1))
        assert got is not None
        return got

    await writer.on_frame((0, 1), FrameState.RENDERING, 1, "frames/ignored.png")
    r = await row()
    assert (r.state, r.attempt, r.asset, r.withheld_check, r.failure) == (
        "rendering",
        1,
        None,
        None,
        None,
    )

    await writer.log(
        audit(1, Verdict.FAIL, Check.TEXT_IN_FRAME, Check.UNSCRIPTED_PERSON), "frames/1.png"
    )
    await writer.on_frame((0, 1), FrameState.WITHHELD, 1, "frames/1.png")
    r = await row()
    # the first failed hard check in Check order, never the asset of a frame that wasn't accepted
    assert (r.state, r.asset, r.withheld_check) == ("withheld", None, "unscripted_person")

    await writer.on_frame((0, 1), FrameState.FAILED, 2, None)
    r = await row()
    assert (r.state, r.attempt, r.withheld_check, r.failure) == ("failed", 2, None, "render")

    await writer.on_frame((0, 1), FrameState.PASSED, 3, "frames/3.png")
    r = await row()
    assert (r.state, r.asset, r.withheld_check, r.failure) == ("passed", "frames/3.png", None, None)


def test_an_audit_that_could_not_run_withholds_as_audit_error() -> None:
    row = FrameAuditRow(verdict="error", checks=[])
    assert withheld_check(row) == "audit_error"
    assert withheld_check(None) is None


async def test_frame_hooks_give_the_record_s_asset_and_only_an_accepted_state_its_image(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pid, jid = await project(sessions, MemoryStore(), run=False)
    renderer = FakeRenderer()
    renderer.records[((0, 1), 1)] = Record("frames/0-1-1.png")
    log, on_state = frame_hooks(FrameWriter(sessions, pid, jid), renderer, (0, 1))
    await log(audit(1, Verdict.PASS))
    await on_state(FrameState.AUDITING, 1)
    async with sessions() as s:
        assert (await s.get(FrameRow, (pid, 0, 1))).asset is None  # type: ignore[union-attr]
    await on_state(FrameState.PASSED, 1)
    async with sessions() as s:
        frame = await s.get(FrameRow, (pid, 0, 1))
        logged = await s.scalar(select(FrameAuditRow))
    assert frame is not None and frame.asset == "frames/0-1-1.png"
    assert logged is not None and logged.frame_asset == "frames/0-1-1.png"


# --- the sweep and the summary ---------------------------------------------------------------


async def test_the_sweep_fails_frames_cut_off_mid_render_as_restart(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pid, jid = await project(sessions, MemoryStore(), run=False)
    writer = FrameWriter(sessions, pid, jid)
    for n, state in enumerate([FrameState.RENDERING, FrameState.AUDITING, FrameState.WITHHELD], 1):
        await writer.on_frame((0, n), state, 1, None)
    async with sessions() as s, s.begin():
        assert await fail_interrupted_frames(s) == 2
    async with sessions() as s:
        rows = (await s.scalars(select(FrameRow).order_by(FrameRow.shot_number))).all()
    assert [(r.state, r.failure) for r in rows] == [
        ("failed", "restart"),
        ("failed", "restart"),
        ("withheld", None),
    ]


async def test_the_summary_is_the_storyboard_job_never_a_retry(
    sessions: async_sessionmaker[AsyncSession], migrated: str
) -> None:
    pid, _ = await project(sessions, MemoryStore(), run=True)
    async with sessions() as s, s.begin():
        s.add(
            JobRow(
                id=uuid.uuid4(),
                project_id=pid,
                kind=JobKind.FRAME_ATTEMPT,
                state=JobState.FAILED,
                error="x",
            )
        )
    app = create_app(Settings(database_url=migrated), verifier=FakeVerifier(), store=MemoryStore())
    with TestClient(app) as c:
        (summary,) = c.get("/api/v1/projects", headers=auth()).json()
    assert summary["job"]["state"] == "done"


# --- "Try another render" --------------------------------------------------------------------


@pytest.fixture
def scripted(monkeypatch: pytest.MonkeyPatch) -> list[Verdict]:
    """The audit answers each attempt with the next verdict in the list."""
    verdicts: list[Verdict] = []

    async def fake(
        model: Any, frame: RenderedFrame, shot: Shot, screenplay: Any, extraction: Any
    ) -> Audit:
        verdict = verdicts.pop(0)
        failed = (Check.UNSCRIPTED_PERSON,) if verdict is Verdict.FAIL else ()
        a = audit(frame.attempt, verdict, *failed)
        return replace(a, shot=frame.shot, seed=frame.seed)

    monkeypatch.setattr(loop, "audit_frame", fake)
    return verdicts


async def withheld(sessions: async_sessionmaker[AsyncSession]) -> tuple[uuid.UUID, tuple[int, int]]:
    """A planned project whose first shot was withheld after three attempts."""
    pid, jid = await project(sessions, MemoryStore(), run=True)
    async with sessions() as s:
        plan = load_plan((await s.get(ProjectRow, pid)).plan)  # type: ignore[union-attr]
    first = plan.shots[0]
    shot = (first.scene_index, first.number)
    writer = FrameWriter(sessions, pid, jid)
    for n in (1, 2, 3):
        await writer.log(
            replace(audit(n, Verdict.FAIL, Check.UNSCRIPTED_PERSON), shot=shot),
            f"frames/{n}.png",
        )
    await writer.on_frame(shot, FrameState.WITHHELD, 3, None)
    return pid, shot


async def wait_for_job(sessions: async_sessionmaker[AsyncSession], pid: uuid.UUID) -> JobRow:
    """The retry runs in the app's own loop (TestClient's thread): poll its job until it settles."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        async with sessions() as s:
            job = await s.scalar(
                select(JobRow).where(JobRow.project_id == pid, JobRow.kind == JobKind.FRAME_ATTEMPT)
            )
        if job is not None and job.state in (JobState.DONE, JobState.FAILED):
            return job
        await asyncio.sleep(0.05)
    raise AssertionError("the retry's job never settled")


def app_with(
    migrated: str, renderer: FakeRenderer | None, *, model: bool = True, store: bool = True
) -> Any:
    return create_app(
        Settings(database_url=migrated),
        verifier=FakeVerifier(),
        store=MemoryStore() if store else None,
        model=make(Models()) if model else None,
        renderer_factory=(lambda screenplay, extraction: renderer)
        if renderer is not None
        else None,
    )


def post(
    c: TestClient, pid: uuid.UUID, shot: tuple[int, int], user: uuid.UUID = ME
) -> tuple[int, Any]:
    res = c.post(f"/api/v1/projects/{pid}/frames/{shot[0]}/{shot[1]}/attempts", headers=auth(user))
    return res.status_code, res.json()


@pytest.fixture
def client_for(migrated: str) -> Iterator[Any]:
    clients: list[TestClient] = []

    def make_client(**kw: Any) -> TestClient:
        c = TestClient(app_with(migrated, **kw))
        c.__enter__()
        clients.append(c)
        return c

    yield make_client
    for c in clients:
        c.__exit__(None, None, None)


async def test_a_withheld_frame_gets_one_more_attempt_under_its_own_job(
    sessions: async_sessionmaker[AsyncSession],
    client_for: Any,
    scripted: list[Verdict],
    migrated: str,
) -> None:
    pid, shot = await withheld(sessions)
    scripted.append(Verdict.PASS)
    c = client_for(renderer=FakeRenderer())
    status, body = post(c, pid, shot)
    assert status == 202
    assert (body["state"], body["attempt"], body["max_renders"], body["image_url"]) == (
        "rendering",
        4,
        4,
        None,
    )
    job = await wait_for_job(sessions, pid)
    assert (job.state, job.progress, job.stage) == (JobState.DONE, 100, "rendering")
    (frame,) = c.get(f"/api/v1/projects/{pid}/frames", headers=auth()).json()
    assert (frame["state"], frame["attempt"], frame["failure"]) == ("passed", 4, None)
    assert frame["image_url"] == f"https://signed/frames/{shot[0]}-{shot[1]}-4.png?e=3600"
    assert [a["attempt"] for a in frame["audits"]] == [1, 2, 3, 4]  # every attempt, oldest first
    assert [a["verdict"] for a in frame["audits"]] == ["fail", "fail", "fail", "pass"]
    assert "frame_asset" not in frame["audits"][0]


async def test_a_renderer_error_fails_the_frame_and_the_job(
    sessions: async_sessionmaker[AsyncSession],
    client_for: Any,
    scripted: list[Verdict],
    migrated: str,
) -> None:
    pid, shot = await withheld(sessions)
    c = client_for(renderer=FakeRenderer(fail=True))
    assert post(c, pid, shot)[0] == 202
    job = await wait_for_job(sessions, pid)
    assert (job.state, job.error) == (JobState.FAILED, "The renderer failed on this frame.")
    async with sessions() as s:
        frame = await s.get(FrameRow, (pid, *shot))
    assert frame is not None and (frame.state, frame.attempt, frame.failure) == (
        "failed",
        4,
        "render",
    )


async def test_a_failure_before_the_loop_still_fails_the_frame(
    sessions: async_sessionmaker[AsyncSession], migrated: str, scripted: list[Verdict]
) -> None:
    pid, shot = await withheld(sessions)

    def broken(screenplay: Any, extraction: Any) -> Any:
        raise RuntimeError("no renderer today")

    app = create_app(
        Settings(database_url=migrated),
        verifier=FakeVerifier(),
        store=MemoryStore(),
        model=make(Models()),
        renderer_factory=broken,
    )
    with TestClient(app) as c:
        assert post(c, pid, shot)[0] == 202
        job = await wait_for_job(sessions, pid)
    assert job.state == JobState.FAILED
    async with sessions() as s:
        frame = await s.get(FrameRow, (pid, *shot))
    assert frame is not None and (frame.state, frame.failure) == ("failed", "render")


async def test_only_a_withheld_or_failed_frame_can_be_retried(
    sessions: async_sessionmaker[AsyncSession], client_for: Any
) -> None:
    # A frame left auditing would be swept to failed (restart) when the app starts, and a failed
    # frame can be retried (T066); a passed one can't.
    pid, shot = await withheld(sessions)
    async with sessions() as s, s.begin():
        frame = await s.get(FrameRow, (pid, *shot))
        assert frame is not None
        frame.state, frame.withheld_check, frame.asset = "passed", None, "frames/3.png"
    c = client_for(renderer=FakeRenderer())
    assert post(c, pid, shot) == (409, {"error": "not_withheld"})


async def test_a_failed_frame_can_be_retried_and_its_failure_is_cleared(
    sessions: async_sessionmaker[AsyncSession], client_for: Any, scripted: list[Verdict]
) -> None:
    # T066 (verify.md §5 FAILED -> RENDERING): a frame whose renderer failed gets another attempt.
    pid, shot = await withheld(sessions)
    async with sessions() as s, s.begin():
        frame = await s.get(FrameRow, (pid, *shot))
        assert frame is not None
        frame.state, frame.withheld_check, frame.failure = "failed", None, "render"
    scripted.append(Verdict.PASS)
    status, body = post(client_for(renderer=FakeRenderer()), pid, shot)
    assert status == 202 and (body["state"], body["attempt"], body["failure"]) == (
        "rendering",
        4,
        None,
    )
    await wait_for_job(sessions, pid)
    async with sessions() as s:
        frame = await s.get(FrameRow, (pid, *shot))
    assert frame is not None and (frame.state, frame.failure) == ("passed", None)


async def test_nothing_is_written_without_a_renderer_a_model_or_a_store(
    sessions: async_sessionmaker[AsyncSession], client_for: Any
) -> None:
    pid, shot = await withheld(sessions)
    assert post(client_for(renderer=None), pid, shot) == (503, {"error": "renderer_unavailable"})
    assert post(client_for(renderer=FakeRenderer(), model=False), pid, shot) == (
        503,
        {"error": "renderer_unavailable"},
    )
    assert post(client_for(renderer=FakeRenderer(), store=False), pid, shot) == (
        503,
        {"error": "storage_unavailable"},
    )
    async with sessions() as s:
        frame = await s.get(FrameRow, (pid, *shot))
        jobs = (await s.scalars(select(JobRow).where(JobRow.kind == JobKind.FRAME_ATTEMPT))).all()
    assert frame is not None and (frame.state, frame.attempt) == ("withheld", 3)
    assert jobs == []


async def test_someone_else_s_or_a_missing_frame_is_404(
    sessions: async_sessionmaker[AsyncSession], client_for: Any
) -> None:
    pid, shot = await withheld(sessions)
    c = client_for(renderer=FakeRenderer())
    assert post(c, pid, shot, user=SOMEONE) == (404, {"error": "not_found"})
    assert post(c, pid, (shot[0], 999)) == (404, {"error": "not_found"})
    assert post(c, pid, ("x", 1)) == (404, {"error": "not_found"})  # type: ignore[arg-type]
    assert post(c, uuid.uuid4(), shot) == (404, {"error": "not_found"})
    assert post(c, pid, (2**31, 1)) == (404, {"error": "not_found"})  # beyond int4: still 404
    assert post(c, pid, (shot[0], 2**40)) == (404, {"error": "not_found"})


async def test_a_repeated_request_finds_the_frame_already_moving(
    sessions: async_sessionmaker[AsyncSession], client_for: Any, scripted: list[Verdict]
) -> None:
    pid, shot = await withheld(sessions)
    scripted.append(Verdict.FAIL)
    renderer = HeldRenderer()  # held, so the frame is still moving when the second request lands
    c = client_for(renderer=renderer)
    assert post(c, pid, shot)[0] == 202
    assert post(c, pid, shot) == (409, {"error": "not_withheld"})  # one attempt per frame at a time
    renderer.release.set()
    await wait_for_job(sessions, pid)
    async with sessions() as s:
        jobs = (await s.scalars(select(JobRow).where(JobRow.kind == JobKind.FRAME_ATTEMPT))).all()
    assert len(jobs) == 1


async def test_a_409_comes_before_any_503(
    sessions: async_sessionmaker[AsyncSession], client_for: Any
) -> None:
    pid, shot = await withheld(sessions)
    async with sessions() as s, s.begin():
        frame = await s.get(FrameRow, (pid, *shot))
        assert frame is not None
        frame.state, frame.withheld_check, frame.asset = "passed", None, "frames/3.png"
    assert post(client_for(renderer=None, model=False, store=False), pid, shot) == (
        409,
        {"error": "not_withheld"},
    )


async def test_an_audit_that_raises_mid_attempt_still_settles_frame_and_job(
    sessions: async_sessionmaker[AsyncSession],
    client_for: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid, shot = await withheld(sessions)

    async def exploding(*args: Any) -> Audit:
        raise RuntimeError("the audit fell over")

    monkeypatch.setattr(loop, "audit_frame", exploding)
    c = client_for(renderer=FakeRenderer())
    assert post(c, pid, shot)[0] == 202
    job = await wait_for_job(sessions, pid)
    assert job.state == JobState.FAILED
    async with sessions() as s:
        frame = await s.get(FrameRow, (pid, *shot))
    assert frame is not None and (frame.state, frame.failure) == ("failed", "render")
