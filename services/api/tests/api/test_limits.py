"""T069: the hosted demo's limits on the routes that spend (docs/design/limits.md §4, §6; web.md
§6). A fake verifier, an in-memory store, the real test Postgres."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.frames.model import FrameRow
from app.jobs import JobKind, JobRow
from app.limits.usage import LlmUsageRow, this_month
from app.main import create_app
from app.projects.model import ProjectRow
from tests.api.test_read import auth, project
from tests.fakes import FakeVerifier, MemoryStore
from tests.frames.test_t021 import FakeRenderer, withheld
from tests.projects.test_pipeline import GOOD_PDF, Models, make

pytestmark = pytest.mark.db

PDF = b"%PDF-1.7\n" + b"x" * 200  # not openable: the page count can't read it, the job would


def app(migrated: str, store: MemoryStore, **limits: Any) -> Any:
    return create_app(
        Settings(database_url=migrated, **limits),
        verifier=FakeVerifier(),
        store=store,
        model=make(Models()),
        renderer_factory=lambda screenplay, extraction: FakeRenderer(),
    )


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def client_with(
    migrated: str, store: MemoryStore, sessions: async_sessionmaker[AsyncSession]
) -> Iterator[Any]:
    clients: list[TestClient] = []

    def make_client(**limits: Any) -> TestClient:
        c = TestClient(app(migrated, store, **limits))
        clients.append(c.__enter__())
        return c

    yield make_client
    for c in clients:
        c.__exit__(None, None, None)


def upload(c: TestClient, data: bytes = PDF) -> tuple[int, Any]:
    files = {"file": ("script.pdf", data, "application/pdf")}
    res = c.post("/api/v1/projects", files=files, headers=auth())
    return res.status_code, res.json()


async def spent(sessions: async_sessionmaker[AsyncSession], tokens: int) -> None:
    async with sessions() as s, s.begin():
        s.add(LlmUsageRow(month=this_month(datetime.now(UTC)), tokens=tokens, calls=1))


async def counts(sessions: async_sessionmaker[AsyncSession]) -> tuple[int, int]:
    async with sessions() as s:
        projects = await s.scalar(select(func.count()).select_from(ProjectRow))
        jobs = await s.scalar(select(func.count()).select_from(JobRow))
    return projects or 0, jobs or 0


# --- the upload --------------------------------------------------------------------------


async def test_at_the_monthly_budget_an_upload_is_refused_and_nothing_is_stored(
    client_with: Any, sessions: async_sessionmaker[AsyncSession], store: MemoryStore
) -> None:
    await spent(sessions, 1_000)
    c = client_with(llm_monthly_token_cap=1_000)
    assert upload(c) == (429, {"error": "llm_budget_spent"})
    assert store.objects == {} and await counts(sessions) == (0, 0)


async def test_under_the_budget_an_upload_goes_through(
    client_with: Any, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await spent(sessions, 999)
    assert upload(client_with(llm_monthly_token_cap=1_000))[0] == 202


async def test_the_uploads_of_a_day_are_capped_per_account(
    client_with: Any, sessions: async_sessionmaker[AsyncSession], store: MemoryStore
) -> None:
    c = client_with(uploads_per_day=2)
    assert upload(c)[0] == 202 and upload(c)[0] == 202
    assert upload(c) == (429, {"error": "upload_limit", "per_day": 2})
    assert (await counts(sessions))[0] == 2 and len(store.objects) == 2


async def test_a_script_over_the_page_limit_is_refused_before_storing(
    client_with: Any, sessions: async_sessionmaker[AsyncSession], store: MemoryStore
) -> None:
    c = client_with(upload_max_pages=1)  # GOOD_PDF has two pages
    assert upload(c, GOOD_PDF) == (413, {"error": "too_many_pages", "max_pages": 1})
    assert store.objects == {} and await counts(sessions) == (0, 0)
    assert upload(client_with(upload_max_pages=2), GOOD_PDF)[0] == 202


async def test_a_pdf_the_page_count_cannot_open_is_left_to_the_job(client_with: Any) -> None:
    assert upload(client_with(upload_max_pages=1), PDF)[0] == 202


async def test_every_limit_is_off_when_unset(
    client_with: Any, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await spent(sessions, 10**12)
    c = client_with()
    assert [upload(c, GOOD_PDF)[0] for _ in range(4)] == [202] * 4


# --- Try another render and Make the comic ---------------------------------------------------


async def test_at_the_budget_try_another_render_is_refused_and_the_frame_untouched(
    client_with: Any, sessions: async_sessionmaker[AsyncSession]
) -> None:
    pid, shot = await withheld(sessions)
    await spent(sessions, 5)
    c = client_with(llm_monthly_token_cap=5)
    res = c.post(f"/api/v1/projects/{pid}/frames/{shot[0]}/{shot[1]}/attempts", headers=auth())
    assert (res.status_code, res.json()) == (429, {"error": "llm_budget_spent"})
    async with sessions() as s:
        frame = await s.get(FrameRow, (pid, *shot))
        attempts = await s.scalar(
            select(func.count()).select_from(JobRow).where(JobRow.kind == JobKind.FRAME_ATTEMPT)
        )
    assert frame is not None and (frame.state, frame.attempt) == ("withheld", 3) and attempts == 0


async def test_at_the_budget_make_the_comic_is_refused(
    client_with: Any, sessions: async_sessionmaker[AsyncSession], store: MemoryStore
) -> None:
    pid, _ = await project(sessions, store, run=True)
    await spent(sessions, 5)
    c = client_with(llm_monthly_token_cap=5)
    res = c.post(f"/api/v1/projects/{pid}/comic", headers=auth())
    assert (res.status_code, res.json()) == (429, {"error": "llm_budget_spent"})
    async with sessions() as s:
        comics = await s.scalar(
            select(func.count()).select_from(JobRow).where(JobRow.kind == JobKind.COMIC)
        )
    assert comics == 0


# --- the meter -------------------------------------------------------------------------------


def test_the_apps_own_model_counts_its_usage(migrated: str) -> None:
    built = create_app(
        Settings(database_url=migrated, nebius_api_key="k"), verifier=FakeVerifier(), store=None
    )
    with TestClient(built):
        assert built.state.model is not None and built.state.model.on_usage is not None
