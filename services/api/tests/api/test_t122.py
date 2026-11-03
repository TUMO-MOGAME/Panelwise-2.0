"""T122: the reads that sign many links sign them in one call (storyboard.md §6 T122, §9 T122).
Responses are unchanged; only how the links are made."""

import uuid
from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.frames.model import FrameRow
from app.main import create_app
from app.storage import StorageError
from tests.api.test_comic import (
    app_with,
    passing,  # noqa: F401  # pyright: ignore[reportUnusedImport] (autouse)
    settle,
)
from tests.api.test_read import auth, get, project
from tests.fakes import FakeVerifier, MemoryStore

pytestmark = pytest.mark.db


class CountingStore(MemoryStore):
    """Records each signing call: a batch's paths in `batches`, a single path in `singles`."""

    def __init__(self) -> None:
        super().__init__()
        self.batches: list[list[str]] = []
        self.singles: list[str] = []

    async def signed_url(self, path: str, expires_in_s: int) -> str:
        self.singles.append(path)
        return f"https://signed/{path}?e={expires_in_s}"

    async def signed_urls(self, paths: Sequence[str], expires_in_s: int) -> list[str]:
        self.batches.append(list(paths))
        return [f"https://signed/{p}?e={expires_in_s}" for p in paths]


class BrokenBatch(MemoryStore):
    async def signed_urls(self, paths: Sequence[str], expires_in_s: int) -> list[str]:
        raise StorageError("signed_urls: storage could not sign 1 of 2")


async def _frames(sessions: async_sessionmaker[AsyncSession], store: MemoryStore) -> uuid.UUID:
    pid, jid = await project(sessions, store, run=True)
    rows = [
        ("passed", "frames/a.png"),
        ("withheld", None),
        ("warned", "frames/b.png"),
        ("passed", "frames/c.png"),
    ]
    async with sessions() as s, s.begin():
        for n, (state, asset) in enumerate(rows, 1):
            s.add(
                FrameRow(
                    project_id=pid, scene_index=0, shot_number=n, state=state, attempt=1,
                    job_id=jid, asset=asset,
                    withheld_check="unscripted_person" if state == "withheld" else None,
                )
            )  # fmt: skip
    return pid


async def test_the_frames_are_signed_in_one_call(
    migrated: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    store = CountingStore()
    pid = await _frames(sessions, store)
    app = create_app(Settings(database_url=migrated), verifier=FakeVerifier(), store=store)
    with TestClient(app) as c:
        status, frames = get(c, f"/{pid}/frames")

    assert status == 200
    assert store.batches == [["frames/a.png", "frames/b.png", "frames/c.png"]]
    assert store.singles == []
    assert [f["image_url"] for f in frames] == [
        "https://signed/frames/a.png?e=3600",
        None,
        "https://signed/frames/b.png?e=3600",
        "https://signed/frames/c.png?e=3600",
    ]


async def test_no_accepted_frame_signs_nothing(
    migrated: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    store = CountingStore()
    pid, jid = await project(sessions, store, run=True)
    async with sessions() as s, s.begin():
        s.add(
            FrameRow(
                project_id=pid, scene_index=0, shot_number=1, state="rendering", attempt=1,
                job_id=jid, asset=None,
            )
        )  # fmt: skip
    app = create_app(Settings(database_url=migrated), verifier=FakeVerifier(), store=store)
    with TestClient(app) as c:
        status, frames = get(c, f"/{pid}/frames")

    assert (status, [f["image_url"] for f in frames]) == (200, [None])
    assert (store.batches, store.singles) == ([], [])


async def test_a_failed_batch_is_503_for_the_frames(
    migrated: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    pid = await _frames(sessions, MemoryStore())
    app = create_app(Settings(database_url=migrated), verifier=FakeVerifier(), store=BrokenBatch())
    with TestClient(app) as c:
        assert get(c, f"/{pid}/frames") == (503, {"error": "storage_unavailable"})


async def test_the_comic_s_pages_and_pdf_are_signed_in_one_call(
    migrated: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    store = CountingStore()
    pid, _ = await project(sessions, store, run=True)
    with TestClient(app_with(migrated, store, renderer=True)) as c:
        assert c.post(f"/api/v1/projects/{pid}/comic", headers=auth()).status_code == 202
        body = settle(c, pid)
        store.batches.clear()
        res = c.get(f"/api/v1/projects/{pid}/comic", headers=auth())

    made = res.json()["comic"]
    (paths,) = store.batches
    assert store.singles == []
    assert paths[-1].endswith(".pdf")
    assert [p["image_url"] for p in made["pages"]] == [
        f"https://signed/{p}?e=3600" for p in paths[:-1]
    ]
    assert made["pdf_url"].startswith(f"https://signed/{paths[-1]}?e=3600&download=")  # T126
    assert body["comic"]["pdf_url"] == made["pdf_url"]


class FailingLater(CountingStore):
    """Signs while the comic is made, then fails every batch once `broken` is set."""

    broken = False

    async def signed_urls(self, paths: Sequence[str], expires_in_s: int) -> list[str]:
        if self.broken:
            raise StorageError("signed_urls: storage could not sign 1 of 2")
        return await super().signed_urls(paths, expires_in_s)


async def test_a_failed_batch_is_503_for_the_comic(
    migrated: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    store = FailingLater()
    pid, _ = await project(sessions, store, run=True)
    with TestClient(app_with(migrated, store, renderer=True)) as c:
        assert c.post(f"/api/v1/projects/{pid}/comic", headers=auth()).status_code == 202
        settle(c, pid)
        store.broken = True
        res = c.get(f"/api/v1/projects/{pid}/comic", headers=auth())

    assert (res.status_code, res.json()) == (503, {"error": "storage_unavailable"})
