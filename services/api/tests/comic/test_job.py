"""T064: the comic job (comic.md §4a, §9 The comic job). A real Postgres, the sketch renderer (it
draws at any size and records before returning), a scripted audit, an in-memory store."""

import asyncio
import hashlib
import io
import uuid
from dataclasses import replace
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from PIL import Image
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.comic import job as comic_job
from app.comic.job import (
    COMIC_LAYOUT_FAILED,
    COMIC_LAYOUT_FAILED_ANY,
    COMIC_RENDER_FAILED,
    COMIC_RENDERER_DOWN,
    COMIC_UNEXPECTED,
    ComicRefused,
    run_comic_job,
    start_comic,
)
from app.comic.layout import layout_geometry
from app.comic.model import ComicError
from app.comic.rows import ComicRow
from app.frames.check import SketchRenderer
from app.frames.model import FrameAuditRow, FrameRow
from app.frames.repo import audits_of
from app.jobs import JobKind, JobRow, JobState
from app.projects.codec import load_plan, load_screenplay
from app.projects.model import ProjectRow
from app.shots import Shot
from app.verify import loop
from app.verify.audit import seed_for
from app.verify.model import Audit, Check, RenderedFrame, Verdict
from tests.api.test_read import ME, SOMEONE, project
from tests.conftest import API
from tests.fakes import MemoryStore
from tests.frames.test_t021 import audit
from tests.projects.test_pipeline import Models, make

pytestmark = pytest.mark.db

type Key = tuple[int, int]


class Sizes(SketchRenderer):
    """The sketch renderer, remembering every size it was asked for, in order."""

    def __init__(self, store: MemoryStore) -> None:
        super().__init__(store)
        self.asked: list[tuple[Key, int, int, int]] = []

    async def render(
        self, shot: Shot, attempt: int, seed: int, width: int, height: int
    ) -> RenderedFrame:
        self.asked.append(((shot.scene_index, shot.number), attempt, width, height))
        return await super().render(shot, attempt, seed, width, height)


class Script:
    """The audit's answers: each panel's next scripted verdict (PASS when none is left); every
    call recorded as (panel, attempt, seed)."""

    def __init__(self) -> None:
        self.verdicts: dict[Key, list[Verdict]] = {}
        self.calls: list[tuple[Key, int, int]] = []


@pytest.fixture
def scripted(monkeypatch: pytest.MonkeyPatch) -> Script:
    script = Script()

    async def fake(
        model: Any, frame: RenderedFrame, shot: Shot, screenplay: Any, extraction: Any
    ) -> Audit:
        script.calls.append((frame.shot, frame.attempt, frame.seed))
        queue = script.verdicts.get(frame.shot, [])
        verdict = queue.pop(0) if queue else Verdict.PASS
        failed = (Check.UNSCRIPTED_PERSON,) if verdict is Verdict.FAIL else ()
        return replace(audit(frame.attempt, verdict, *failed), shot=frame.shot, seed=frame.seed)

    monkeypatch.setattr(loop, "audit_frame", fake)
    return script


async def planned(sessions: async_sessionmaker[AsyncSession], store: MemoryStore) -> ProjectRow:
    pid, _ = await project(sessions, store, run=True)
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
    assert row is not None
    return row


async def make_comic(
    sessions: async_sessionmaker[AsyncSession],
    store: MemoryStore,
    pid: uuid.UUID,
    renderer: SketchRenderer | None = None,
    concurrency: int = 1,
) -> JobRow:
    async with sessions() as s, s.begin():
        started = await start_comic(s, pid, ME, renderer=True, store=True)
    drawn = renderer or SketchRenderer(store)
    await run_comic_job(
        started.id,
        sessions=sessions,
        store=store,
        model=make(Models()),
        factory=lambda screenplay, extraction: drawn,
        concurrency=concurrency,
    )
    async with sessions() as s:
        done = await s.get(JobRow, started.id)
    assert done is not None
    return done


async def comic_audits(sessions: async_sessionmaker[AsyncSession]) -> list[FrameAuditRow]:
    async with sessions() as s:
        rows = await s.scalars(
            select(FrameAuditRow).order_by(
                FrameAuditRow.scene_index, FrameAuditRow.shot_number, FrameAuditRow.attempt
            )
        )
        return list(rows)


# --- a comic, end to end ----------------------------------------------------------------------


async def test_every_panel_is_drawn_at_its_rect_audited_as_comic_and_stored_by_content(
    sessions: async_sessionmaker[AsyncSession],
    scripted: Script,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)
    plan, screenplay = load_plan(row.plan), load_screenplay(row.screenplay)  # type: ignore[arg-type]
    book = layout_geometry(plan, screenplay)
    rects = {(p.scene_index, p.shot_number): p.rect for pg in book.pages for p in pg.panels}
    first = (plan.shots[0].scene_index, plan.shots[0].number)
    scripted.verdicts[first] = [Verdict.FAIL, Verdict.FAIL, Verdict.FAIL]  # withheld; the rest pass
    progress: list[int] = []
    real_progress = comic_job._progress  # pyright: ignore[reportPrivateUsage]

    async def watch(sessions: Any, job_id: uuid.UUID, value: int) -> None:
        progress.append(value)
        await real_progress(sessions, job_id, value)

    monkeypatch.setattr(comic_job, "_progress", watch)
    renderer = Sizes(store)

    job = await make_comic(sessions, store, row.id, renderer)

    assert (job.kind, job.state, job.progress, job.error) == (JobKind.COMIC, "done", 100, None)
    # Every request at exactly its panel's rect, panels in plan order, three tries for the first.
    keys = [(s.scene_index, s.number) for s in plan.shots]
    assert [k for k, *_ in renderer.asked] == [first, first, first, *keys[1:]]
    assert all((w, h) == rects[k][2:] for k, _, w, h in renderer.asked)
    assert progress == sorted(progress) and progress[-1] == 90 and len(progress) == len(keys)
    # Logged as the comic's, never a frames row, and the storyboard's audit log doesn't see them.
    logged = await comic_audits(sessions)
    assert {a.target for a in logged} == {"comic"} and len(logged) == len(renderer.asked)
    async with sessions() as s:
        assert await s.scalar(select(func.count()).select_from(FrameRow)) == 0
        assert await audits_of(s, row.id) == {}
        comic = await s.get(ComicRow, row.id)
    assert comic is not None and comic.job_id == job.id
    # Pages and PDF at their content hashes; frame_url a Storage path, none for the withheld panel.
    for path in [*comic.pages, comic.pdf]:
        data, _ = store.objects[path]
        assert path.startswith("comics/") and hashlib.sha256(data).hexdigest() in path
    panels = {tuple(p["shot"]): p for pg in comic.layout["pages"] for p in pg["panels"]}
    assert panels[first]["withheld"] and "frame_url" not in panels[first]
    for key in keys[1:]:
        assert not panels[key]["withheld"] and panels[key]["frame_url"] in store.objects
    page = Image.open(io.BytesIO(store.objects[comic.pages[0]][0]))
    assert page.size == (1988, 3075)


async def test_a_second_job_reuses_accepted_panels_and_numbers_new_attempts_after_the_last(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)
    plan = load_plan(row.plan)  # type: ignore[arg-type]
    first = (plan.shots[0].scene_index, plan.shots[0].number)
    scripted.verdicts[first] = [Verdict.FAIL, Verdict.FAIL, Verdict.FAIL]
    one = await make_comic(sessions, store, row.id)
    before = len(scripted.calls)
    renderer = Sizes(store)

    two = await make_comic(sessions, store, row.id, renderer)

    assert (one.state, two.state) == ("done", "done")
    # Only the withheld panel is drawn and audited again, at attempt 4 with attempt 4's seed.
    assert [(k, a) for k, a, *_ in renderer.asked] == [(first, 4)]
    assert scripted.calls[before:] == [(first, 4, seed_for(plan.shots[0], 4))]
    async with sessions() as s:
        comic = await s.get(ComicRow, row.id)
    assert comic is not None and comic.job_id == two.id
    assert all(not p["withheld"] for pg in comic.layout["pages"] for p in pg["panels"])


async def test_a_stored_panel_of_another_size_is_drawn_again(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)
    plan = load_plan(row.plan)  # type: ignore[arg-type]
    await make_comic(sessions, store, row.id)
    first = (plan.shots[0].scene_index, plan.shots[0].number)
    (accepted,) = [
        a for a in await comic_audits(sessions) if (a.scene_index, a.shot_number) == first
    ]
    buffer = io.BytesIO()
    Image.new("RGB", (64, 36), "white").save(buffer, format="PNG")
    store.objects[accepted.frame_asset] = (buffer.getvalue(), "image/png")  # another size
    renderer = Sizes(store)

    job = await make_comic(sessions, store, row.id, renderer)

    assert job.state == "done"
    assert [(k, a) for k, a, *_ in renderer.asked] == [
        (first, 2)
    ]  # only that panel, after attempt 1


# --- failures ---------------------------------------------------------------------------------


class Broken(Sizes):
    """A renderer that raises for the panels in `fails` (every panel when None)."""

    def __init__(self, store: MemoryStore, fails: set[Key] | None = None) -> None:
        super().__init__(store)
        self.fails = fails

    async def render(
        self, shot: Shot, attempt: int, seed: int, width: int, height: int
    ) -> RenderedFrame:
        key = (shot.scene_index, shot.number)
        if self.fails is None or key in self.fails:
            self.asked.append((key, attempt, width, height))
            raise RuntimeError("the pencil broke")
        return await super().render(shot, attempt, seed, width, height)


async def test_a_renderer_that_fails_every_panel_stops_and_keeps_the_previous_comic(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)
    plan = load_plan(row.plan)  # type: ignore[arg-type]
    first = (plan.shots[0].scene_index, plan.shots[0].number)
    scripted.verdicts[first] = [Verdict.FAIL, Verdict.FAIL, Verdict.FAIL]
    one = await make_comic(sessions, store, row.id)

    # The second job reuses every panel the first accepted, so only the withheld one is drawn
    # again: one failure with none drawn is min(3, panels to render), and the renderer is down.
    broken = Broken(store)
    two = await make_comic(sessions, store, row.id, broken)
    assert (two.state, two.error) == ("failed", COMIC_RENDERER_DOWN)
    assert [asked[0] for asked in broken.asked] == [first]
    async with sessions() as s:
        comic = await s.get(ComicRow, row.id)
    assert comic is not None and comic.job_id == one.id


async def test_a_renderer_down_from_the_start_stops_after_three_panels(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)
    broken = Broken(store)
    job = await make_comic(sessions, store, row.id, broken)
    assert (job.state, job.error) == ("failed", COMIC_RENDERER_DOWN)
    panels = len(load_plan(row.plan).shots)  # type: ignore[arg-type]
    assert len(broken.asked) == min(3, panels)  # no further panel tried


async def test_one_failed_panel_gets_its_card_and_the_comic_is_made(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)
    plan = load_plan(row.plan)  # type: ignore[arg-type]
    last = (plan.shots[-1].scene_index, plan.shots[-1].number)
    job = await make_comic(sessions, store, row.id, Broken(store, {last}))
    assert (job.state, job.error, job.progress) == ("done", None, 100)
    async with sessions() as s:
        comic = await s.get(ComicRow, row.id)
    assert comic is not None and comic.job_id == job.id
    panels = [p for page in comic.layout["pages"] for p in page["panels"]]
    by_shot = {tuple(p["shot"]): p for p in panels}
    assert by_shot[last]["withheld"] is True and "frame_url" not in by_shot[last]
    assert all(p["withheld"] is False for key, p in by_shot.items() if key != last)


async def test_a_panel_drawn_at_the_wrong_size_fails_at_once(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)

    class Ignores(Sizes):
        async def render(
            self, shot: Shot, attempt: int, seed: int, width: int, height: int
        ) -> RenderedFrame:
            return await super().render(shot, attempt, seed, 1280, 720)

    renderer = Ignores(store)
    job = await make_comic(sessions, store, row.id, renderer)
    assert (job.state, job.error) == ("failed", COMIC_RENDER_FAILED)
    assert len(renderer.asked) == 1  # stopped at the first panel, not after every other


async def kept(sessions: async_sessionmaker[AsyncSession], pid: uuid.UUID) -> uuid.UUID | None:
    async with sessions() as s:
        comic = await s.get(ComicRow, pid)
    return None if comic is None else comic.job_id


async def test_an_audit_error_is_unexpected_not_a_renderer_failure(
    sessions: async_sessionmaker[AsyncSession],
    scripted: Script,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)
    plan = load_plan(row.plan)  # type: ignore[arg-type]
    first = (plan.shots[0].scene_index, plan.shots[0].number)
    scripted.verdicts[first] = [Verdict.FAIL, Verdict.FAIL, Verdict.FAIL]
    one = await make_comic(sessions, store, row.id)  # the withheld panel is audited again next

    async def down(*_: Any) -> Audit:
        raise RuntimeError("the judge is down")

    monkeypatch.setattr(loop, "audit_frame", down)
    job = await make_comic(sessions, store, row.id)
    assert (job.state, job.error) == ("failed", COMIC_UNEXPECTED)
    assert await kept(sessions, row.id) == one.id


async def test_a_lettering_failure_names_the_shot_as_the_web_does(
    sessions: async_sessionmaker[AsyncSession],
    scripted: Script,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)
    screenplay = load_screenplay(row.screenplay)  # type: ignore[arg-type]
    one = await make_comic(sessions, store, row.id)

    def no_room(*_: Any) -> Any:
        raise ComicError("scene 1, shot 1: no room", shot=(1, 1))

    monkeypatch.setattr(comic_job, "place_lettering", no_room)
    job = await make_comic(sessions, store, row.id)
    shot_id = f"{screenplay.scenes[1].number}.1"
    assert (job.state, job.error) == ("failed", COMIC_LAYOUT_FAILED.format(shot_id=shot_id))

    def nameless(*_: Any) -> Any:
        raise ComicError("no shot named")

    monkeypatch.setattr(comic_job, "place_lettering", nameless)
    job = await make_comic(sessions, store, row.id)
    assert job.error == COMIC_LAYOUT_FAILED_ANY
    assert await kept(sessions, row.id) == one.id


def test_a_shot_outside_the_screenplay_falls_back_to_the_message_that_names_none() -> None:
    error = ComicError("scene 99", shot=(99, 1))
    assert comic_job._layout_message(error, None) == COMIC_LAYOUT_FAILED_ANY  # pyright: ignore[reportPrivateUsage]


# --- start_comic: the checks in order, nothing written ----------------------------------------


async def comic_jobs(sessions: async_sessionmaker[AsyncSession]) -> int:
    async with sessions() as s:
        found = await s.scalar(
            select(func.count()).select_from(JobRow).where(JobRow.kind == JobKind.COMIC)
        )
    return found or 0


async def refused(
    sessions: async_sessionmaker[AsyncSession],
    pid: uuid.UUID,
    owner: uuid.UUID = ME,
    *,
    renderer: bool = True,
    store: bool = True,
) -> str:
    with pytest.raises(ComicRefused) as caught:
        async with sessions() as s, s.begin():
            await start_comic(s, pid, owner, renderer=renderer, store=store)
    return caught.value.code


async def test_start_comic_answers_each_check_in_order_and_writes_nothing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)
    unplanned, _ = await project(sessions, store, run=False)
    assert await refused(sessions, uuid.uuid4()) == "not_found"
    assert await refused(sessions, row.id, SOMEONE) == "not_found"
    assert await refused(sessions, unplanned, renderer=False, store=False) == "not_ready"
    assert await refused(sessions, row.id, renderer=False, store=False) == "renderer_unavailable"
    assert await refused(sessions, row.id, store=False) == "storage_unavailable"
    assert await comic_jobs(sessions) == 0
    async with sessions() as s, s.begin():
        s.add(
            JobRow(id=uuid.uuid4(), project_id=row.id, kind=JobKind.COMIC, state=JobState.RUNNING)
        )
    assert await refused(sessions, row.id, renderer=False) == "comic_running"


async def test_two_clicks_at_once_make_one_job(sessions: async_sessionmaker[AsyncSession]) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)

    async def click() -> str:
        try:
            async with sessions() as s, s.begin():
                await start_comic(s, row.id, ME, renderer=True, store=True)
                await asyncio.sleep(0.05)  # hold the lock while the other click waits on it
        except ComicRefused as refusal:
            return refusal.code
        return "started"

    assert sorted(await asyncio.gather(click(), click())) == ["comic_running", "started"]
    assert await comic_jobs(sessions) == 1


# --- the migration ------------------------------------------------------------------------------


async def test_the_migration_downgrades_with_comics_present(
    sessions: async_sessionmaker[AsyncSession],
    migrated: str,
    scripted: Script,
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)
    await make_comic(sessions, store, row.id)
    config = Config(str(API / "alembic.ini"))
    config.set_main_option("script_location", str(API / "migrations"))
    config.attributes["database_url"] = migrated
    await asyncio.to_thread(command.downgrade, config, "0004")
    try:
        async with sessions() as s:
            assert await s.scalar(text("SELECT to_regclass('public.comics')")) is None
            assert await s.scalar(text("SELECT count(*) FROM jobs WHERE kind = 'comic'")) == 0
    finally:
        await asyncio.to_thread(command.upgrade, config, "head")
    async with sessions() as s:
        assert await s.scalar(select(func.count()).select_from(FrameAuditRow)) == 0


# --- T073: panels as many at once as the renderer allows ---------------------------------------


class Overlap(Sizes):
    """The sketch renderer, counting how many renders are in flight at once."""

    def __init__(self, store: MemoryStore) -> None:
        super().__init__(store)
        self.now = self.most = 0

    async def render(
        self, shot: Shot, attempt: int, seed: int, width: int, height: int
    ) -> RenderedFrame:
        self.now += 1
        self.most = max(self.most, self.now)
        try:
            await asyncio.sleep(0.02)  # long enough for a second panel to start
            return await super().render(shot, attempt, seed, width, height)
        finally:
            self.now -= 1


async def test_two_panels_are_in_the_renderer_at_once_and_never_three(
    sessions: async_sessionmaker[AsyncSession], scripted: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)
    progress: list[int] = []
    real_progress = comic_job._progress  # pyright: ignore[reportPrivateUsage]

    async def watch(sessions: Any, job_id: uuid.UUID, value: int) -> None:
        progress.append(value)
        await real_progress(sessions, job_id, value)

    monkeypatch.setattr(comic_job, "_progress", watch)
    renderer = Overlap(store)
    job = await make_comic(sessions, store, row.id, renderer, concurrency=2)
    assert (job.state, job.progress, job.error) == ("done", 100, None)
    assert renderer.most == 2
    assert progress == sorted(progress) and progress[-1] == 90


async def test_the_comic_is_the_same_at_any_concurrency(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    made: list[tuple[Any, list[str]]] = []
    for concurrency in (1, 2):
        store = MemoryStore()
        row = await planned(sessions, store)
        job = await make_comic(sessions, store, row.id, Overlap(store), concurrency=concurrency)
        assert job.state == "done"
        async with sessions() as s:
            comic = await s.get(ComicRow, row.id)
        assert comic is not None
        made.append((comic.layout, list(comic.pages)))
    # The pages and layout, byte for byte; not the PDF, whose bytes carry its creation time.
    assert made[0] == made[1]


async def test_a_wrong_size_panel_cancels_the_one_in_flight_and_starts_no_other(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)

    class Ignores(Overlap):
        async def render(
            self, shot: Shot, attempt: int, seed: int, width: int, height: int
        ) -> RenderedFrame:
            return await super().render(shot, attempt, seed, 1280, 720)

    renderer = Ignores(store)
    job = await make_comic(sessions, store, row.id, renderer, concurrency=2)
    assert (job.state, job.error) == ("failed", COMIC_RENDER_FAILED)
    assert len(renderer.asked) <= 2  # the two started together; none after the failure
    assert renderer.now == 0  # nothing left running


async def test_a_concurrency_below_one_is_refused(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    store = MemoryStore()
    row = await planned(sessions, store)
    with pytest.raises(ValueError, match="concurrency"):
        await make_comic(sessions, store, row.id, concurrency=0)


async def test_a_panel_still_in_its_audit_counts_as_drawn_so_the_renderer_isn_t_down(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """T073 review: the first panel draws and sits in a slow audit while the others fail fast.
    One panel reached its audit, so the renderer works: failed cards, not COMIC_RENDERER_DOWN."""
    store = MemoryStore()
    row = await planned(sessions, store)
    keys = [(s.scene_index, s.number) for s in load_plan(row.plan).shots]  # type: ignore[arg-type]
    assert len(keys) == 3
    monkeypatch.setattr(comic_job, "DOWN_AFTER", 2)  # both others failing would be enough
    first = keys[0]

    async def slow_for_the_first(
        model: Any, frame: RenderedFrame, shot: Shot, screenplay: Any, extraction: Any
    ) -> Audit:
        if frame.shot == first:
            await asyncio.sleep(0.3)
        return replace(audit(frame.attempt, Verdict.PASS), shot=frame.shot, seed=frame.seed)

    monkeypatch.setattr(loop, "audit_frame", slow_for_the_first)

    class FailsButTheFirst(Overlap):
        async def render(
            self, shot: Shot, attempt: int, seed: int, width: int, height: int
        ) -> RenderedFrame:
            if (shot.scene_index, shot.number) != first:
                await asyncio.sleep(0.1)  # fails after the first panel has reached its audit
                raise RuntimeError("renderer error")
            return await super().render(shot, attempt, seed, width, height)

    job = await make_comic(sessions, store, row.id, FailsButTheFirst(store), concurrency=2)
    assert (job.state, job.error) == ("done", None)


async def test_max_renders_is_each_panel_s_attempts(
    sessions: async_sessionmaker[AsyncSession], scripted: Script
) -> None:
    """T071: RENDER_MAX_ATTEMPTS=1 draws a failing panel once (comic.md §6 `max_renders`)."""
    store = MemoryStore()
    row = await planned(sessions, store)
    plan = load_plan(row.plan)  # type: ignore[arg-type]
    keys = [(s.scene_index, s.number) for s in plan.shots]
    scripted.verdicts = {k: [Verdict.FAIL] * 3 for k in keys}
    async with sessions() as s, s.begin():
        started = await start_comic(s, row.id, ME, renderer=True, store=True)
    renderer = Sizes(store)
    await run_comic_job(
        started.id,
        sessions=sessions,
        store=store,
        model=make(Models()),
        factory=lambda screenplay, extraction: renderer,
        max_renders=1,
    )
    assert [k for k, *_ in renderer.asked] == keys
    assert all(attempt == 1 for _, attempt, _, _ in renderer.asked)
