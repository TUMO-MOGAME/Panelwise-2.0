"""The read endpoints and frames: web.md §6 (rows marked T047, *API internals: the reads*)."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.frames.model import FrameAuditRow, FrameRow
from app.main import create_app
from app.projects.codec import load_extraction, load_plan, load_screenplay
from app.projects.job import run_job
from app.projects.model import ProjectRow
from app.projects.repo import create_upload
from app.projects.views import entity_views, lines_view, report_view, scene_views, shot_views
from app.verify.schema import FrameDescription
from tests.fakes import FakeVerifier, MemoryStore
from tests.projects.test_pipeline import GOOD_PDF, Models, make

pytestmark = pytest.mark.db

ME, SOMEONE = uuid.uuid4(), uuid.uuid4()


def auth(user: uuid.UUID = ME) -> dict[str, str]:
    return {"Authorization": f"Bearer user-{user}"}


async def project(
    sessions: async_sessionmaker[AsyncSession], store: MemoryStore, *, run: bool
) -> tuple[uuid.UUID, uuid.UUID]:
    pid = uuid.uuid4()
    path = f"scripts/{ME}/{pid}.pdf"
    await store.put(path, GOOD_PDF, "application/pdf")
    async with sessions() as s, s.begin():
        _, job = await create_upload(s, project_id=pid, owner=ME, title="Lighthouse", pdf_path=path)
    if run:
        await run_job(job.id, sessions=sessions, store=store, model=make(Models()))
    return pid, job.id


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def client(
    migrated: str, store: MemoryStore, sessions: async_sessionmaker[AsyncSession]
) -> Iterator[TestClient]:
    app = create_app(Settings(database_url=migrated), verifier=FakeVerifier(), store=store)
    with TestClient(app) as c:
        yield c


def get(c: TestClient, path: str, user: uuid.UUID = ME) -> tuple[int, Any]:
    res = c.get(f"/api/v1/projects{path}", headers=auth(user))
    return res.status_code, res.json()


async def test_a_planned_project_reads_as_the_builders_make_it(
    client: TestClient, store: MemoryStore, sessions: async_sessionmaker[AsyncSession]
) -> None:
    pid, _ = await project(sessions, store, run=True)
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
    assert row is not None
    screenplay, extraction, plan = (
        load_screenplay(row.screenplay),
        load_extraction(row.extraction),
        load_plan(row.plan),
    )

    status, body = get(client, f"/{pid}")
    assert status == 200
    assert body["scene_list"] == [v.model_dump(mode="json") for v in scene_views(screenplay, plan)]
    assert body["entities"] == [v.model_dump(mode="json") for v in entity_views(extraction)]
    assert body["report"] == report_view(extraction, plan).model_dump(mode="json")
    assert (body["pages"], body["scenes"], body["shots"], body["frames"]) == (
        screenplay.page_count,
        len(screenplay.scenes),
        len(plan.shots),
        None,
    )
    assert body["job"]["state"] == "done"

    assert get(client, f"/{pid}/lines") == (200, lines_view(screenplay).model_dump(mode="json"))
    expected = [v.model_dump(mode="json") for v in shot_views(screenplay, extraction, plan)]
    assert get(client, f"/{pid}/shots") == (200, expected)
    assert get(client, f"/{pid}/frames") == (200, [])  # no rows until T021 writes them


async def test_before_it_runs_the_parts_are_null_and_the_pages_not_ready(
    client: TestClient, store: MemoryStore, sessions: async_sessionmaker[AsyncSession]
) -> None:
    pid, _ = await project(sessions, store, run=False)
    status, body = get(client, f"/{pid}")
    assert status == 200
    assert (body["scene_list"], body["entities"], body["report"]) == (None, None, None)
    assert get(client, f"/{pid}/lines") == (409, {"error": "not_ready"})
    assert get(client, f"/{pid}/shots") == (409, {"error": "not_ready"})


async def test_someone_elses_or_a_missing_or_a_malformed_id_is_the_same_404(
    client: TestClient, store: MemoryStore, sessions: async_sessionmaker[AsyncSession]
) -> None:
    pid, _ = await project(sessions, store, run=True)
    for path in ("", "/lines", "/shots", "/frames"):
        assert get(client, f"/{pid}{path}", user=SOMEONE) == (404, {"error": "not_found"})
        assert get(client, f"/{uuid.uuid4()}{path}") == (404, {"error": "not_found"})
        assert get(client, f"/not-a-uuid{path}") == (404, {"error": "not_found"})
    assert client.get(f"/api/v1/projects/{pid}").status_code == 401  # no token


async def test_frames_come_only_from_rows_and_images_only_when_accepted(
    client: TestClient, store: MemoryStore, sessions: async_sessionmaker[AsyncSession]
) -> None:
    pid, jid = await project(sessions, store, run=True)
    states = [
        ("passed", "frames/a.png"),
        ("warned", "frames/b.png"),
        ("withheld", None),
        ("rendering", None),
        ("auditing", None),
        ("failed", None),
    ]
    async with sessions() as s, s.begin():
        for n, (state, asset) in enumerate(states, 1):
            s.add(
                FrameRow(
                    project_id=pid,
                    scene_index=0,
                    shot_number=n,
                    state=state,
                    attempt=1,
                    job_id=jid,
                    asset=asset,
                    withheld_check="unscripted_person" if state == "withheld" else None,
                )
            )
    status, frames = get(client, f"/{pid}/frames")
    assert status == 200
    assert [f["state"] for f in frames] == [s for s, _ in states]
    assert [f["image_url"] for f in frames] == [
        "https://signed/frames/a.png?e=3600",
        "https://signed/frames/b.png?e=3600",
        None,
        None,
        None,
        None,
    ]
    status, body = get(client, f"/{pid}")
    # total is the plan's shot count, not the rows: most shots have no row yet (web.md §6).
    assert body["frames"] == {"settled": 4, "total": body["shots"], "withheld": 1, "active": 2}
    assert body["frames"]["total"] != len(states)  # the plan's shots, not the rows
    (summary,) = client.get("/api/v1/projects", headers=auth()).json()
    assert summary["frames"] == body["frames"]


async def test_the_database_keeps_an_asset_off_a_frame_that_isnt_accepted(
    store: MemoryStore, sessions: async_sessionmaker[AsyncSession]
) -> None:
    from sqlalchemy.exc import IntegrityError

    pid, jid = await project(sessions, store, run=False)
    with pytest.raises(IntegrityError):
        async with sessions() as s, s.begin():
            s.add(
                FrameRow(
                    project_id=pid,
                    scene_index=0,
                    shot_number=1,
                    state="withheld",
                    attempt=1,
                    job_id=jid,
                    asset="frames/leak.png",
                )
            )


async def test_a_users_extra_render_never_reads_attempt_4_of_3(
    client: TestClient, store: MemoryStore, sessions: async_sessionmaker[AsyncSession]
) -> None:
    pid, jid = await project(sessions, store, run=True)
    async with sessions() as s, s.begin():
        s.add(
            FrameRow(
                project_id=pid,
                scene_index=0,
                shot_number=1,
                state="rendering",
                attempt=4,
                job_id=jid,
            )
        )
    (frame,) = get(client, f"/{pid}/frames")[1]
    assert (frame["attempt"], frame["max_renders"]) == (4, 4)


class BrokenStore(MemoryStore):
    async def signed_url(self, path: str, expires_in_s: int) -> str:
        from app.storage import StorageError

        raise StorageError("signed_url: storage answered 500")


@pytest.mark.parametrize("store_kind", ["none", "broken"])
async def test_an_accepted_frame_without_working_storage_is_503(
    migrated: str, sessions: async_sessionmaker[AsyncSession], store_kind: str
) -> None:
    store = MemoryStore()
    pid, jid = await project(sessions, store, run=True)
    async with sessions() as s, s.begin():
        s.add(
            FrameRow(
                project_id=pid,
                scene_index=0,
                shot_number=1,
                state="passed",
                attempt=1,
                job_id=jid,
                asset="frames/a.png",
            )
        )
    serving = None if store_kind == "none" else BrokenStore()
    app = create_app(Settings(database_url=migrated), verifier=FakeVerifier(), store=serving)
    with TestClient(app) as c:
        assert get(c, f"/{pid}/frames") == (503, {"error": "storage_unavailable"})


# A frame audited since T107 reads: DescriptionView carries `signature_text` (web.md §6). Before
# it, the view refused the field and GET …/frames answered 500 for every storyboard drawn after
# 2026-10-18.

T107 = FrameDescription.model_validate(
    {
        "people": [{"position": "left", "appearance": "a child with braids"}],
        "setting": "exterior",
        "light": "day",
        "shot_size": "wide",
        "objects": [],
        "signature": True,
        "signature_text": ["J. Blake"],
        "has_text": False,
        "text": [],
    }
).model_dump(mode="json")


async def test_a_frame_audited_since_t107_reads_with_its_signature_text(
    client: TestClient, store: MemoryStore, sessions: async_sessionmaker[AsyncSession]
) -> None:
    pid, jid = await project(sessions, store, run=True)
    async with sessions() as s, s.begin():
        s.add(
            FrameRow(
                project_id=pid, scene_index=0, shot_number=1, state="passed", attempt=1,
                job_id=jid, asset="frames/a.png",
            )
        )  # fmt: skip
        s.add(
            FrameAuditRow(
                project_id=pid, job_id=jid, scene_index=0, shot_number=1, attempt=1, seed=11,
                frame_asset="frames/a.png", description=T107, judgement=None,
                checks=[{"check": "signature", "severity": "soft", "ok": False, "detail": "x"}],
                positions={}, verdict="warn", models=["m"], prompt_tokens=0, completion_tokens=0,
            )
        )  # fmt: skip

    status, frames = get(client, f"/{pid}/frames")

    assert status == 200
    (audit,) = frames[0]["audits"]
    assert audit["description"]["signature_text"] == ["J. Blake"]
    assert audit["description"]["signature"] is True


async def test_a_description_from_before_t107_reads_with_none(
    client: TestClient, store: MemoryStore, sessions: async_sessionmaker[AsyncSession]
) -> None:
    pid, jid = await project(sessions, store, run=True)
    old = {k: v for k, v in T107.items() if k != "signature_text"}
    async with sessions() as s, s.begin():
        s.add(
            FrameRow(
                project_id=pid, scene_index=0, shot_number=1, state="passed", attempt=1,
                job_id=jid, asset="frames/a.png",
            )
        )  # fmt: skip
        s.add(
            FrameAuditRow(
                project_id=pid, job_id=jid, scene_index=0, shot_number=1, attempt=1, seed=11,
                frame_asset="frames/a.png", description=old, judgement=None, checks=[],
                positions={}, verdict="pass", models=["m"], prompt_tokens=0, completion_tokens=0,
            )
        )  # fmt: skip

    status, frames = get(client, f"/{pid}/frames")

    assert status == 200
    assert frames[0]["audits"][0]["description"]["signature_text"] == []


def test_every_field_the_describer_returns_is_one_the_view_reads() -> None:
    """The guard against the next one: a field added to FrameDescription (the describer's answer,
    stored as is) must be added to DescriptionView too, or every new frame's read is a 500."""
    from app.api.v1.schemas import DescriptionView

    missing = set(FrameDescription.model_fields) - set(DescriptionView.model_fields)
    assert missing == set()
