"""T027: GET /projects/{id}/storyboard/pdf (web.md §6; storyboard.md §3.4 Delivery). The app with
the in-memory store and a real Postgres; frames rows written as the storyboard job leaves them."""

import uuid
from collections.abc import Iterator
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.frames.model import FrameAuditRow, FrameRow
from app.main import create_app
from app.projects.codec import load_plan
from app.projects.model import ProjectRow
from tests.api.test_read import SOMEONE, auth, project
from tests.fakes import FakeVerifier, MemoryStore

pytestmark = pytest.mark.db


class CountingStore(MemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.gets: list[str] = []

    async def get(self, path: str) -> bytes:
        self.gets.append(path)
        return await super().get(path)


@pytest.fixture
def store() -> CountingStore:
    return CountingStore()


@pytest.fixture
def client(migrated: str, store: CountingStore) -> Iterator[TestClient]:
    app = create_app(Settings(database_url=migrated), verifier=FakeVerifier(), store=store)
    with TestClient(app) as c:
        yield c


def png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (1280, 720), (120, 120, 120)).save(buffer, "PNG")
    return buffer.getvalue()


async def settled(
    sessions: async_sessionmaker[AsyncSession],
    store: MemoryStore,
    pid: uuid.UUID,
    jid: uuid.UUID,
    *,
    last: str = "withheld",
) -> list[tuple[int, int]]:
    """A row per plan shot, as the storyboard job leaves them: every shot passed and drawn, but
    the last one, which is `last`; each with its audit."""
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
    assert row is not None and row.plan is not None
    shots = [(sh.scene_index, sh.number) for sh in load_plan(row.plan).shots]
    async with sessions() as s, s.begin():
        for i, (scene, number) in enumerate(shots):
            state = last if i == len(shots) - 1 else "passed"
            asset = f"frames/{scene}-{number}.png" if state == "passed" else None
            if asset is not None:
                await store.put(asset, png(), "image/png")
            s.add(
                FrameRow(
                    project_id=pid,
                    scene_index=scene,
                    shot_number=number,
                    state=state,
                    attempt=1,
                    job_id=jid,
                    asset=asset,
                    withheld_check="unscripted_person" if state == "withheld" else None,
                )
            )
            if state in ("passed", "withheld"):
                ok = state == "passed"
                s.add(
                    FrameAuditRow(
                        project_id=pid,
                        job_id=jid,
                        scene_index=scene,
                        shot_number=number,
                        attempt=1,
                        seed=11,
                        frame_asset=f"frames/{scene}-{number}-a1.png",
                        description=None,
                        judgement=None,
                        checks=[{"check": "unscripted_person", "severity": "hard", "ok": ok}],
                        positions={},
                        verdict="pass" if ok else "fail",
                        models=["m"],
                        prompt_tokens=0,
                        completion_tokens=0,
                    )
                )
    return shots


def pdf(c: TestClient, pid: uuid.UUID, user: uuid.UUID | None = None) -> tuple[int, Any]:
    headers = auth() if user is None else auth(user)
    res = c.get(f"/api/v1/projects/{pid}/storyboard/pdf", headers=headers)
    return res.status_code, res.json()


async def test_a_settled_storyboard_answers_a_signed_pdf_built_once(
    client: TestClient, sessions: async_sessionmaker[AsyncSession], store: CountingStore
) -> None:
    pid, jid = await project(sessions, store, run=True)
    shots = await settled(sessions, store, pid, jid)
    store.gets.clear()
    status, body = pdf(client, pid)
    assert status == 200, body
    path = body["pdf_url"].removeprefix("https://signed/").split("?")[0]
    assert body["pdf_url"].endswith("%20storyboard.pdf")  # T126: saved under the screenplay's title
    assert path.startswith("storyboards/") and path.endswith(".pdf")
    data, content_type = store.objects[path]
    assert data.startswith(b"%PDF") and content_type == "application/pdf"
    # Every passed frame read; the withheld one never (it has no asset to read).
    assert sorted(store.gets) == sorted(f"frames/{s}-{n}.png" for s, n in shots[:-1])

    store.gets.clear()
    assert pdf(client, pid) == (200, body)
    assert store.gets == []  # a store hit: no frame read


async def test_a_failed_frame_still_exports_with_its_card(
    client: TestClient, sessions: async_sessionmaker[AsyncSession], store: CountingStore
) -> None:
    pid, jid = await project(sessions, store, run=True)
    await settled(sessions, store, pid, jid, last="failed")
    status, body = pdf(client, pid)
    assert status == 200 and body["pdf_url"].startswith("https://signed/storyboards/")


async def test_not_ready_until_every_shot_has_a_settled_row(
    client: TestClient, sessions: async_sessionmaker[AsyncSession], store: CountingStore
) -> None:
    pid, jid = await project(sessions, store, run=True)
    assert pdf(client, pid) == (409, {"error": "not_ready"})  # planned, no frames yet
    await settled(sessions, store, pid, jid, last="rendering")
    assert pdf(client, pid) == (409, {"error": "not_ready"})  # one still in flight


async def test_before_the_job_is_done_it_is_not_ready(
    client: TestClient, sessions: async_sessionmaker[AsyncSession], store: CountingStore
) -> None:
    pid, _ = await project(sessions, store, run=False)
    assert pdf(client, pid) == (409, {"error": "not_ready"})


async def test_someone_elses_or_a_malformed_id_is_not_found(
    client: TestClient, sessions: async_sessionmaker[AsyncSession], store: CountingStore
) -> None:
    pid, jid = await project(sessions, store, run=True)
    await settled(sessions, store, pid, jid)
    assert pdf(client, pid, SOMEONE) == (404, {"error": "not_found"})
    res = client.get("/api/v1/projects/not-a-uuid/storyboard/pdf", headers=auth())
    assert (res.status_code, res.json()) == (404, {"error": "not_found"})


async def test_without_a_store_or_styles_it_is_unavailable(
    migrated: str, sessions: async_sessionmaker[AsyncSession], store: CountingStore
) -> None:
    pid, jid = await project(sessions, store, run=True)
    await settled(sessions, store, pid, jid)
    no_store = create_app(Settings(database_url=migrated), verifier=FakeVerifier(), store=None)
    with TestClient(no_store) as c:
        assert pdf(c, pid) == (503, {"error": "storage_unavailable"})
    app = create_app(Settings(database_url=migrated), verifier=FakeVerifier(), store=store)
    with TestClient(app) as c:
        app.state.styles = None  # as when the styles didn't load at startup
        assert pdf(c, pid) == (503, {"error": "styles_unavailable"})
