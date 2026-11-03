"""T071: the re-audit of stored drawings (verify.md §6 The re-audit, §9). A real Postgres, an
in-memory store, a scripted audit: nothing is drawn and nothing is written."""

import io
import logging
import uuid
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.frames.model import AuditTarget, FrameAuditRow
from app.frames.writer import FrameWriter
from app.projects.codec import load_plan
from app.projects.model import ProjectRow
from app.shots import Shot
from app.verify import reaudit as module
from app.verify.model import Audit, Check, RenderedFrame, Verdict
from app.verify.reaudit import Reaudit, line, reaudit, summary
from tests.api.test_read import project
from tests.fakes import MemoryStore
from tests.frames.test_t021 import audit
from tests.projects.test_pipeline import Models, make

pytestmark = pytest.mark.db


def png(width: int, height: int) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(out, "PNG")
    return out.getvalue()


class Scripted:
    """The new audit: PASS for every frame unless told otherwise; every call recorded."""

    def __init__(self) -> None:
        self.fail: set[tuple[int, int]] = set()
        self.calls: list[tuple[tuple[int, int], int, int, int, int]] = []

    async def __call__(
        self, model: Any, frame: RenderedFrame, shot: Shot, screenplay: Any, extraction: Any
    ) -> Audit:
        assert (shot.scene_index, shot.number) == frame.shot
        self.calls.append((frame.shot, frame.attempt, frame.seed, frame.width, frame.height))
        if frame.shot in self.fail:
            return replace(audit(frame.attempt, Verdict.FAIL, Check.TEXT_IN_FRAME), shot=frame.shot)
        return replace(audit(frame.attempt, Verdict.PASS), shot=frame.shot)


@pytest.fixture
def scripted(monkeypatch: pytest.MonkeyPatch) -> Scripted:
    fake = Scripted()
    monkeypatch.setattr(module, "audit_frame", fake)
    return fake


async def logged(
    sessions: async_sessionmaker[AsyncSession], store: MemoryStore
) -> tuple[uuid.UUID, list[tuple[int, int]]]:
    """A planned project whose first two shots each have two failed storyboard attempts and one
    comic attempt logged, every drawing stored."""
    pid, jid = await project(sessions, store, run=True)
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
    assert row is not None and row.plan is not None
    keys = [(s.scene_index, s.number) for s in load_plan(row.plan).shots][:2]
    board = FrameWriter(sessions, pid, jid)
    comic = FrameWriter(sessions, pid, jid, target=AuditTarget.COMIC)
    for key in keys:
        for attempt in (1, 2):
            path = f"frames/{key[0]}-{key[1]}-{attempt}.png"
            await store.put(path, png(64, 36), "image/png")
            failed = audit(attempt, Verdict.FAIL, Check.TEXT_IN_FRAME)
            await board.log(replace(failed, shot=key, seed=500 + attempt), path)
        path = f"frames/{key[0]}-{key[1]}-comic.png"
        await store.put(path, png(40, 50), "image/png")
        await comic.log(replace(audit(1, Verdict.FAIL, Check.TEXT_IN_FRAME), shot=key), path)
    return pid, keys


async def audit_rows(sessions: async_sessionmaker[AsyncSession]) -> int:
    async with sessions() as s:
        return await s.scalar(select(func.count()).select_from(FrameAuditRow)) or 0


async def test_every_row_of_a_target_is_audited_again_in_order_and_nothing_is_written(
    sessions: async_sessionmaker[AsyncSession], scripted: Scripted
) -> None:
    store = MemoryStore()
    pid, keys = await logged(sessions, store)
    scripted.fail = {keys[1]}
    rows_before, objects_before = await audit_rows(sessions), dict(store.objects)

    rows = await reaudit(sessions, store, make(Models()), pid, target=AuditTarget.STORYBOARD)

    assert [(r.shot, r.attempt, r.target) for r in rows] == [
        (keys[0], 1, "storyboard"), (keys[0], 2, "storyboard"),
        (keys[1], 1, "storyboard"), (keys[1], 2, "storyboard"),
    ]  # fmt: skip
    assert [(r.before, r.after) for r in rows] == [
        (Verdict.FAIL, Verdict.PASS), (Verdict.FAIL, Verdict.PASS),
        (Verdict.FAIL, Verdict.FAIL), (Verdict.FAIL, Verdict.FAIL),
    ]  # fmt: skip
    assert rows[2].failed == (Check.TEXT_IN_FRAME,) and rows[0].failed == ()
    # The row's seed, and the drawing's own size.
    assert [(c[2], c[3], c[4]) for c in scripted.calls] == [(501, 64, 36), (502, 64, 36)] * 2
    assert await audit_rows(sessions) == rows_before and store.objects == objects_before


async def test_no_target_means_both_and_limit_takes_the_first_rows(
    sessions: async_sessionmaker[AsyncSession], scripted: Scripted
) -> None:
    store = MemoryStore()
    pid, _ = await logged(sessions, store)
    both = await reaudit(sessions, store, make(Models()), pid)
    assert [r.target for r in both] == ["comic"] * 2 + ["storyboard"] * 4
    assert scripted.calls[0][3:] == (40, 50)
    first = await reaudit(sessions, store, make(Models()), pid, limit=3)
    assert [(r.target, r.attempt) for r in first] == [(r.target, r.attempt) for r in both[:3]]


async def test_a_drawing_that_is_gone_is_reported_and_skipped(
    sessions: async_sessionmaker[AsyncSession],
    scripted: Scripted,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = MemoryStore()
    pid, keys = await logged(sessions, store)
    del store.objects[f"frames/{keys[0][0]}-{keys[0][1]}-1.png"]
    with caplog.at_level(logging.WARNING, logger="app.verify.reaudit"):
        rows = await reaudit(sessions, store, make(Models()), pid, target=AuditTarget.STORYBOARD)
    assert len(rows) == 3 and (keys[0], 1) not in {(r.shot, r.attempt) for r in rows}
    assert any("gone" in r.getMessage() for r in caplog.records)


def test_summary_counts_before_and_after_and_each_hard_check_after() -> None:
    rows = [
        Reaudit((0, 1), 1, "storyboard", Verdict.FAIL, Verdict.PASS, ()),
        Reaudit((0, 1), 2, "storyboard", Verdict.FAIL, Verdict.WARN, ()),
        Reaudit((0, 2), 1, "comic", Verdict.FAIL, Verdict.FAIL, (Check.TEXT_IN_FRAME,)),
        Reaudit(
            (0, 3), 1, "comic", Verdict.ERROR, Verdict.FAIL,
            (Check.UNSCRIPTED_PERSON, Check.TEXT_IN_FRAME),
        ),
    ]  # fmt: skip
    text = summary(rows)
    assert "4 drawings" in text
    assert "before: pass 0, warn 0, fail 3, error 1" in text
    assert "after:  pass 1, warn 1, fail 2, error 0" in text
    assert "text_in_frame 2" in text and "unscripted_person 1" in text


def test_a_line_names_the_shot_as_the_web_does_with_an_arrow_and_the_failed_checks() -> None:
    scenes = [SimpleNamespace(number="1"), SimpleNamespace(number="6")]
    passed = Reaudit((1, 4), 1, "comic", Verdict.FAIL, Verdict.PASS, ())
    failed = Reaudit((0, 2), 3, "storyboard", Verdict.FAIL, Verdict.FAIL, (Check.TEXT_IN_FRAME,))
    assert line(passed, scenes) == "6.4 a1 comic: fail → pass"  # type: ignore[arg-type]
    assert line(failed, scenes) == "1.2 a3 storyboard: fail → fail (text_in_frame)"  # type: ignore[arg-type]
