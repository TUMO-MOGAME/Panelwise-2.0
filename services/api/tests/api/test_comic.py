"""T064: POST and GET /projects/{id}/comic (web.md §6; comic.md §4a). The app with the sketch
renderer as its factory, a scripted audit, the in-memory store, a real Postgres."""

import time
import uuid
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.comic.job import COMIC_RESTARTED
from app.core.config import Settings
from app.frames.check import SketchRenderer
from app.frames.model import FrameAuditRow
from app.jobs import JobKind, JobRow, JobState
from app.jobs.model import RESTARTED
from app.main import create_app
from app.projects.codec import load_screenplay
from app.projects.model import ProjectRow
from app.script import Dialogue
from app.shots import Shot
from app.verify import loop
from app.verify.model import Audit, Check, RenderedFrame, Verdict
from tests.api.test_read import ME, SOMEONE, auth, project
from tests.fakes import FakeVerifier, MemoryStore
from tests.frames.test_t021 import audit

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def passing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(
        model: Any, frame: RenderedFrame, shot: Shot, screenplay: Any, extraction: Any
    ) -> Audit:
        return replace(audit(frame.attempt, Verdict.PASS), shot=frame.shot, seed=frame.seed)

    monkeypatch.setattr(loop, "audit_frame", fake)


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


def app_with(migrated: str, store: MemoryStore | None, *, renderer: bool) -> Any:
    def factory(screenplay: Any, extraction: Any) -> SketchRenderer:
        assert store is not None
        return SketchRenderer(store)

    return create_app(
        Settings(database_url=migrated, nebius_api_key="k"),
        verifier=FakeVerifier(),
        store=store,
        renderer_factory=factory if renderer else None,
    )


@pytest.fixture
def client(
    migrated: str, store: MemoryStore, sessions: async_sessionmaker[AsyncSession]
) -> Iterator[TestClient]:
    with TestClient(app_with(migrated, store, renderer=True)) as c:
        yield c


def comic(c: TestClient, pid: uuid.UUID, user: uuid.UUID = ME) -> tuple[int, Any]:
    res = c.get(f"/api/v1/projects/{pid}/comic", headers=auth(user))
    return res.status_code, res.json()


def settle(c: TestClient, pid: uuid.UUID) -> Any:
    """The job runs in the app's own loop (TestClient's thread): poll until it settles."""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status, body = comic(c, pid)
        assert status == 200
        if body["job"] and body["job"]["state"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError("the comic job never settled")


async def test_make_the_comic_then_read_it_signed_and_traceable(
    client: TestClient, store: MemoryStore, sessions: async_sessionmaker[AsyncSession]
) -> None:
    pid, _ = await project(sessions, store, run=True)
    status, before = comic(client, pid)
    assert status == 200
    assert (before["can_make"], before["job"], before["comic"]) == (True, None, None)
    assert before["shots"] >= 1

    res = client.post(f"/api/v1/projects/{pid}/comic", headers=auth())
    assert res.status_code == 202
    assert (res.json()["job"]["state"], res.json()["job"]["progress"]) == ("running", 0)

    body = settle(client, pid)
    assert (body["job"]["state"], body["job"]["progress"]) == ("done", 100)
    made = body["comic"]
    assert made["pdf_url"].startswith("https://signed/comics/")
    assert ".pdf?e=3600&download=" in made["pdf_url"]  # T126: saved under the screenplay's title
    assert made["pdf_url"].endswith("%20comic.pdf")
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
    assert row is not None and row.screenplay is not None
    screenplay = load_screenplay(row.screenplay)
    for page in made["pages"]:
        assert page["image_url"].startswith("https://signed/comics/")
        assert (page["width"], page["height"]) == (1988, 3075)
        for panel in page["panels"]:
            scene_index = next(
                s.index for s in screenplay.scenes if panel["shot_id"].startswith(f"{s.number}.")
            )
            lettering = panel["lettering"]
            kinds = [item["kind"] for item in lettering]
            # The scene caption first, then the spoken lines in element order.
            assert "scene" not in kinds[1:]
            spoken = [item for item in lettering if item["kind"] != "scene"]
            for item in spoken:
                element = next(
                    e
                    for e in screenplay.scenes[scene_index].elements
                    if isinstance(e, Dialogue) and e.text == item["text"]
                )
                cue = (
                    element.cue
                    if element.extension is None
                    else f"{element.cue} ({element.extension})"
                )
                assert (item["speaker"], item["cue"]) == (element.cue, cue)
                assert item["span"]["line_start"] == element.span.line_start
    cues = [i["cue"] for pg in made["pages"] for p in pg["panels"] for i in p["lettering"]]
    assert any(cue and "(" in cue for cue in cues)  # a cue with its extension, as the script has it


async def test_the_answers_before_anything_is_written(
    migrated: str,
    client: TestClient,
    store: MemoryStore,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    planned, _ = await project(sessions, store, run=True)
    unplanned, _ = await project(sessions, store, run=False)
    post = client.post
    assert post(f"/api/v1/projects/{planned}/comic", headers=auth(SOMEONE)).status_code == 404
    assert post("/api/v1/projects/not-a-uuid/comic", headers=auth()).status_code == 404
    res = post(f"/api/v1/projects/{unplanned}/comic", headers=auth())
    assert (res.status_code, res.json()) == (409, {"error": "not_ready"})
    assert comic(client, unplanned)[0] == 409
    assert comic(client, planned, SOMEONE)[0] == 404
    with TestClient(app_with(migrated, store, renderer=False)) as bare:
        res = bare.post(f"/api/v1/projects/{planned}/comic", headers=auth())
        assert (res.status_code, res.json()) == (503, {"error": "renderer_unavailable"})
        assert (
            bare.get(f"/api/v1/projects/{planned}/comic", headers=auth()).json()["can_make"]
            is False
        )
    with TestClient(app_with(migrated, None, renderer=True)) as storeless:
        res = storeless.post(f"/api/v1/projects/{planned}/comic", headers=auth())
        assert (res.status_code, res.json()) == (503, {"error": "storage_unavailable"})
    async with sessions() as s:
        jobs = await s.scalars(select(JobRow).where(JobRow.kind == JobKind.COMIC))
        assert list(jobs) == []


async def test_a_comic_cut_off_by_a_restart_says_make_it_again_and_never_stands_for_the_project(
    client: TestClient, store: MemoryStore, sessions: async_sessionmaker[AsyncSession]
) -> None:
    pid, _ = await project(sessions, store, run=True)
    async with sessions() as s, s.begin():
        s.add(
            JobRow(
                id=uuid.uuid4(),
                project_id=pid,
                kind=JobKind.COMIC,
                state=JobState.FAILED,
                error=RESTARTED,
            )
        )
    assert comic(client, pid)[1]["job"]["error"] == COMIC_RESTARTED
    (summary,) = client.get("/api/v1/projects", headers=auth()).json()
    assert summary["job"]["state"] == "done"  # the upload's job, not the comic's


async def test_the_route_passes_render_max_attempts_to_the_comic_job(
    migrated: str,
    store: MemoryStore,
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T071: with RENDER_MAX_ATTEMPTS=1 a failing panel is audited once, not three times."""

    async def failing(
        model: Any, frame: RenderedFrame, shot: Shot, screenplay: Any, extraction: Any
    ) -> Audit:
        failed = audit(frame.attempt, Verdict.FAIL, Check.UNSCRIPTED_PERSON)
        return replace(failed, shot=frame.shot, seed=frame.seed)

    monkeypatch.setattr(loop, "audit_frame", failing)
    pid, _ = await project(sessions, store, run=True)

    def factory(screenplay: Any, extraction: Any) -> SketchRenderer:
        return SketchRenderer(store)

    app = create_app(
        Settings(database_url=migrated, nebius_api_key="k", render_max_attempts=1),
        verifier=FakeVerifier(),
        store=store,
        renderer_factory=factory,
    )
    with TestClient(app) as c:
        shots = comic(c, pid)[1]["shots"]
        assert c.post(f"/api/v1/projects/{pid}/comic", headers=auth()).status_code == 202
        assert settle(c, pid)["job"]["state"] == "done"
    async with sessions() as s:
        rows = list(await s.scalars(select(FrameAuditRow).where(FrameAuditRow.project_id == pid)))
    assert len(rows) == shots and {r.attempt for r in rows} == {1}
