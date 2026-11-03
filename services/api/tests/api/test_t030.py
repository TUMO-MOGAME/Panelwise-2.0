"""T030: the hosted demo's image budget, drawings a month from `frame_audits` (docs/design/limits.md
§4, §6, §9; comic.md §4a; web.md §6). A fake verifier, an in-memory store, the test Postgres."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.demo.seed import copy_sample
from app.frames.model import AuditTarget, FrameAuditRow, FrameRow
from app.jobs import JobKind, JobRow
from app.limits.usage import drawings_this_month
from tests.api import test_limits
from tests.api.test_limits import counts, spent, upload
from tests.api.test_read import auth, project
from tests.demo.test_seed import finished
from tests.fakes import MemoryStore
from tests.frames.test_t021 import withheld

pytestmark = pytest.mark.db

# T069's fixtures: an app with the given limits, and its in-memory store.
client_with = test_limits.client_with
store = test_limits.store


async def drawn(
    sessions: async_sessionmaker[AsyncSession], n: int, *, when: datetime | None = None
) -> None:
    """`n` logged drawings, storyboard and comic alternately, stamped `when` (default: now)."""
    pid, jid = await project(sessions, MemoryStore(), run=True)
    async with sessions() as s, s.begin():
        for i in range(n):
            row = FrameAuditRow(
                project_id=pid,
                job_id=jid,
                target=(AuditTarget.STORYBOARD if i % 2 == 0 else AuditTarget.COMIC).value,
                scene_index=0,
                shot_number=1,
                attempt=i + 1,
                seed=i,
                frame_asset=f"frames/{i}.png",
                description=None,
                judgement=None,
                checks=[],
                positions={},
                verdict="pass",
                models=["m"],
                prompt_tokens=1,
                completion_tokens=1,
            )
            if when is not None:
                row.created_at = when
            s.add(row)


async def now_drawn(sessions: async_sessionmaker[AsyncSession]) -> int:
    async with sessions() as s:
        return await drawings_this_month(s)


# --- the count -------------------------------------------------------------------------------


async def test_the_month_counts_every_drawing_of_both_targets_and_not_last_months(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    before = await now_drawn(sessions)
    await drawn(sessions, 3)
    await drawn(sessions, 4, when=datetime.now(UTC) - timedelta(days=40))
    assert await now_drawn(sessions) == before + 3


def test_a_blank_image_cap_in_the_environment_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAGE_MONTHLY_GENERATION_CAP", "")
    assert Settings(_env_file=None).image_monthly_generation_cap is None  # type: ignore[call-arg]
    monkeypatch.setenv("IMAGE_MONTHLY_GENERATION_CAP", "1500")
    assert Settings(_env_file=None).image_monthly_generation_cap == 1500  # type: ignore[call-arg]


# --- the routes ------------------------------------------------------------------------------


async def test_at_the_image_cap_an_upload_is_refused_and_nothing_is_stored(
    client_with: Any,
    sessions: async_sessionmaker[AsyncSession],
    store: MemoryStore,
) -> None:
    await drawn(sessions, 2)
    cap = await now_drawn(sessions)
    projects_before = (await counts(sessions))[0]
    c = client_with(image_monthly_generation_cap=cap)
    assert upload(c) == (429, {"error": "image_budget_spent"})
    assert store.objects == {} and (await counts(sessions))[0] == projects_before


async def test_under_the_image_cap_an_upload_goes_through(
    client_with: Any,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await drawn(sessions, 1)
    cap = await now_drawn(sessions) + 1
    assert upload(client_with(image_monthly_generation_cap=cap))[0] == 202


async def test_the_token_budget_answers_first_when_both_are_spent(
    client_with: Any,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await drawn(sessions, 1)
    await spent(sessions, 10)
    c = client_with(llm_monthly_token_cap=10, image_monthly_generation_cap=1)
    assert upload(c) == (429, {"error": "llm_budget_spent"})


@pytest.mark.parametrize("cap", [None, 0])
async def test_the_image_cap_is_off_when_unset_or_zero(
    client_with: Any,
    sessions: async_sessionmaker[AsyncSession],
    cap: int | None,
) -> None:
    await drawn(sessions, 3)
    assert upload(client_with(image_monthly_generation_cap=cap))[0] == 202


async def test_at_the_image_cap_try_another_render_is_refused_and_the_frame_untouched(
    client_with: Any,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pid, shot = await withheld(sessions)
    c = client_with(image_monthly_generation_cap=await now_drawn(sessions))
    res = c.post(f"/api/v1/projects/{pid}/frames/{shot[0]}/{shot[1]}/attempts", headers=auth())
    assert (res.status_code, res.json()) == (429, {"error": "image_budget_spent"})
    async with sessions() as s:
        frame = await s.get(FrameRow, (pid, *shot))
        attempts = await s.scalar(
            select(func.count()).select_from(JobRow).where(JobRow.kind == JobKind.FRAME_ATTEMPT)
        )
    assert frame is not None and (frame.state, frame.attempt) == ("withheld", 3) and attempts == 0


async def test_at_the_image_cap_make_the_comic_is_refused_with_429_not_500(
    client_with: Any,
    sessions: async_sessionmaker[AsyncSession],
    store: MemoryStore,
) -> None:
    pid, _ = await project(sessions, store, run=True)
    await drawn(sessions, 1)
    c = client_with(image_monthly_generation_cap=await now_drawn(sessions))
    res = c.post(f"/api/v1/projects/{pid}/comic", headers=auth())
    assert (res.status_code, res.json()) == (429, {"error": "image_budget_spent"})
    async with sessions() as s:
        comics = await s.scalar(
            select(func.count()).select_from(JobRow).where(JobRow.kind == JobKind.COMIC)
        )
    assert comics == 0


# --- the judge seed --------------------------------------------------------------------------


async def test_the_judge_seed_spends_none_of_this_months_drawings(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    source = await finished(sessions, comic=False)
    last_month = datetime.now(UTC) - timedelta(days=40)
    async with sessions() as s, s.begin():
        await s.execute(
            update(FrameAuditRow)
            .where(FrameAuditRow.project_id == source)
            .values(created_at=last_month)
        )
    before = await now_drawn(sessions)
    copied = await copy_sample(sessions, source, uuid.uuid4())
    assert copied.copied
    assert await now_drawn(sessions) == before
    async with sessions() as s:
        stamps = set(
            await s.scalars(
                select(FrameAuditRow.created_at).where(
                    FrameAuditRow.project_id == copied.project_id
                )
            )
        )
    assert stamps and all(abs((t - last_month).total_seconds()) < 1 for t in stamps)
