"""T083: the re-check of stored audits (verify.md §6, §9). A real Postgres: today's run_checks on
what the audit already saw and judged; no model, no Storage, nothing written."""

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.frames.model import AuditTarget, FrameAuditRow
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.model import ProjectRow
from app.storyboard.prompt import visible_characters
from app.verify import run_checks
from app.verify.model import Verdict
from app.verify.reaudit import Reaudit
from app.verify.recheck import accepted_shots, recheck
from tests.api.test_read import project
from tests.fakes import MemoryStore
from tests.verify.conftest import described, judged

pytestmark = pytest.mark.db

NOBODY_NOTHING: dict[str, Any] = {"people": [], "objects": []}


def _row(
    pid: uuid.UUID,
    jid: uuid.UUID,
    key: tuple[int, int],
    attempt: int,
    *,
    target: AuditTarget = AuditTarget.STORYBOARD,
    description: dict[str, Any] | None,
    judgement: dict[str, Any] | None,
) -> FrameAuditRow:
    return FrameAuditRow(
        project_id=pid,
        job_id=jid,
        target=target.value,
        scene_index=key[0],
        shot_number=key[1],
        attempt=attempt,
        seed=attempt,
        frame_asset=f"frames/{key}-{attempt}.png",
        description=description,
        judgement=judgement,
        checks=[],
        positions={},
        verdict="fail",
        models=["d", "j"],
        prompt_tokens=1,
        completion_tokens=1,
    )


async def _logged(
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, tuple[int, int], Verdict]:
    """One shot with: a readable storyboard audit, an ERROR (no description), one in an old
    schema, and a readable comic audit. Returns the verdict today's checks give the readable."""
    pid, jid = await project(sessions, MemoryStore(), run=True)
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
    assert row is not None and row.plan is not None
    screenplay = load_screenplay(row.screenplay)  # type: ignore[arg-type]
    extraction = load_extraction(row.extraction)
    shot = load_plan(row.plan).shots[0]
    key = (shot.scene_index, shot.number)
    description = described(**NOBODY_NOTHING)
    judgement = judged(**NOBODY_NOTHING)
    _, today, _ = run_checks(
        shot,
        screenplay.scenes[shot.scene_index],
        description,
        judgement,
        extraction,
        on_screen=visible_characters(shot, screenplay, extraction),
    )
    seen = description.model_dump(mode="json")
    judged_json = judgement.model_dump(mode="json")
    async with sessions() as s, s.begin():
        s.add(_row(pid, jid, key, 1, description=seen, judgement=judged_json))
        s.add(_row(pid, jid, key, 2, description=None, judgement=None))
        s.add(_row(pid, jid, key, 3, description={"bogus": 1}, judgement=judged_json))
        s.add(
            _row(
                pid, jid, key, 1, target=AuditTarget.COMIC, description=seen, judgement=judged_json
            )
        )
    return pid, key, today


async def _count(sessions: async_sessionmaker[AsyncSession]) -> int:
    async with sessions() as s:
        return await s.scalar(select(func.count()).select_from(FrameAuditRow)) or 0


async def test_todays_checks_on_stored_audits_and_the_unreadable_skipped(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pid, key, today = await _logged(sessions)
    before = await _count(sessions)
    rows, skipped = await recheck(sessions, pid, target=AuditTarget.STORYBOARD)
    assert [(r.shot, r.attempt, r.target) for r in rows] == [(key, 1, "storyboard")]
    assert (rows[0].before, rows[0].after) == (Verdict.FAIL, today)
    assert skipped == 2  # the ERROR and the old schema
    assert await _count(sessions) == before  # nothing written


async def test_the_ladder_applies_as_it_does_live(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """T094: recheck demotes the hard checks off the ladder, as the loop does before it logs, so a
    stored WARN isn't reported as a change; None ("all") keeps every hard check."""
    pid, _, today = await _logged(sessions)
    assert today is Verdict.FAIL
    (raw,), _ = await recheck(sessions, pid, target=AuditTarget.STORYBOARD)
    (none,), _ = await recheck(
        sessions, pid, target=AuditTarget.STORYBOARD, withholding=frozenset()
    )
    (kept,), _ = await recheck(
        sessions, pid, target=AuditTarget.STORYBOARD, withholding=frozenset(raw.failed)
    )
    assert raw.failed and raw.after is Verdict.FAIL
    assert (none.after, none.failed) == (Verdict.WARN, ())
    assert (kept.after, kept.failed) == (Verdict.FAIL, raw.failed)


async def test_no_target_means_both(sessions: async_sessionmaker[AsyncSession]) -> None:
    pid, _, _ = await _logged(sessions)
    rows, skipped = await recheck(sessions, pid)
    assert [r.target for r in rows] == ["comic", "storyboard"]
    assert skipped == 2


async def test_no_project_and_no_plan_raise(sessions: async_sessionmaker[AsyncSession]) -> None:
    with pytest.raises(ValueError, match="no such project"):
        await recheck(sessions, uuid.uuid4())
    pid, _ = await project(sessions, MemoryStore(), run=False)
    with pytest.raises(ValueError, match="no shot plan yet"):
        await recheck(sessions, pid)


def test_accepted_shots_counts_shots_per_target() -> None:
    def r(shot: tuple[int, int], target: str, before: Verdict, after: Verdict) -> Reaudit:
        return Reaudit(shot, 1, target, before, after, ())

    rows = [
        r((0, 1), "storyboard", Verdict.FAIL, Verdict.WARN),
        r((0, 1), "storyboard", Verdict.FAIL, Verdict.PASS),  # the same shot again
        r((0, 2), "storyboard", Verdict.PASS, Verdict.PASS),
        r((0, 2), "comic", Verdict.FAIL, Verdict.FAIL),
        r((0, 3), "comic", Verdict.WARN, Verdict.ERROR),
    ]
    assert accepted_shots(rows) == (2, 2)
