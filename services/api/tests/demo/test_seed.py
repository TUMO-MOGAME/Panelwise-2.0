"""T069: the judge seed (docs/design/limits.md §4, §9). A fake Supabase Auth admin API (no
network) and the real test Postgres."""

import json
import uuid
from typing import Any

import httpx2
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.comic.rows import ComicRow
from app.demo.seed import SeedError, copy_sample, ensure_judge, main
from app.frames.model import FrameAuditRow, FrameRow
from app.jobs import JobKind, JobRow, JobState
from app.projects.codec import load_plan
from app.projects.model import ProjectRow
from tests.api.test_read import ME, project
from tests.fakes import MemoryStore

pytestmark = pytest.mark.db

URL, SECRET = "https://sb.test", "sb_secret_never_printed"
EMAIL, PASSWORD = "judge@panelwise.demo", "pw-never-printed"


class FakeAuth:
    """Supabase Auth's admin users endpoints, enough for the seed."""

    def __init__(self, *, existing: bool = False) -> None:
        self.users: dict[str, str] = {}  # email → id
        self.passwords: dict[str, str] = {}
        self.requests: list[httpx2.Request] = []
        if existing:
            self.users[EMAIL] = str(uuid.uuid4())

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        assert request.headers["apikey"] == SECRET
        path = request.url.path
        if request.method == "POST" and path == "/auth/v1/admin/users":
            body = json.loads(request.content)
            assert body["email_confirm"] is True
            if body["email"] in self.users:
                return httpx2.Response(422, json={"error_code": "email_exists"})
            uid = str(uuid.uuid4())
            self.users[body["email"]] = uid
            self.passwords[uid] = body["password"]
            return httpx2.Response(200, json={"id": uid, "email": body["email"]})
        if request.method == "GET" and path == "/auth/v1/admin/users":
            page = int(request.url.params.get("page", "1"))
            listed = [{"id": i, "email": e} for e, i in self.users.items()]
            return httpx2.Response(200, json={"users": listed if page == 1 else []})
        if request.method == "PUT" and path.startswith("/auth/v1/admin/users/"):
            uid = path.rsplit("/", 1)[1]
            sent = json.loads(request.content)
            assert sent["email_confirm"] is True
            self.passwords[uid] = sent["password"]
            return httpx2.Response(200, json={"id": uid})
        return httpx2.Response(404)


def client(auth: FakeAuth) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(transport=httpx2.MockTransport(auth))


# --- the judge's login ------------------------------------------------------------------------


async def test_the_judge_is_created_then_updated_on_a_second_run() -> None:
    auth = FakeAuth()
    async with client(auth) as c:
        first = await ensure_judge(c, URL, SECRET, EMAIL, PASSWORD)
        second = await ensure_judge(c, URL, SECRET, EMAIL, "a-new-password")
    assert first == second == uuid.UUID(auth.users[EMAIL])
    assert auth.passwords[str(first)] == "a-new-password"
    assert [r.method for r in auth.requests] == ["POST", "POST", "GET", "PUT"]


async def test_a_weak_password_is_said_not_mistaken_for_an_existing_judge() -> None:
    def weak(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(422, json={"error_code": "weak_password"})

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(weak)) as c:
        with pytest.raises(SeedError, match="422 weak_password") as raised:
            await ensure_judge(c, URL, SECRET, EMAIL, PASSWORD)
    assert PASSWORD not in str(raised.value)


async def test_an_auth_error_names_the_status_and_never_the_key() -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json={"msg": "bad key"})

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(refuse)) as c:
        with pytest.raises(SeedError, match="401") as raised:
            await ensure_judge(c, URL, SECRET, EMAIL, PASSWORD)
    assert SECRET not in str(raised.value) and PASSWORD not in str(raised.value)


# --- the sample's copy -----------------------------------------------------------------------


async def finished(sessions: async_sessionmaker[AsyncSession], *, comic: bool) -> uuid.UUID:
    """A planned project whose storyboard settled (every shot passed), its audits, a comic."""
    pid, jid = await project(sessions, MemoryStore(), run=True)
    async with sessions() as s:
        row = await s.get(ProjectRow, pid)
    assert row is not None and row.plan is not None
    shots = [(sh.scene_index, sh.number) for sh in load_plan(row.plan).shots]
    async with sessions() as s, s.begin():
        for scene, number in shots:
            s.add(
                FrameRow(
                    project_id=pid,
                    scene_index=scene,
                    shot_number=number,
                    state="passed",
                    attempt=1,
                    job_id=jid,
                    asset=f"frames/{scene}-{number}.png",
                )
            )
            s.add(
                FrameAuditRow(
                    project_id=pid,
                    job_id=jid,
                    scene_index=scene,
                    shot_number=number,
                    attempt=1,
                    seed=1,
                    frame_asset=f"frames/{scene}-{number}.png",
                    description=None,
                    judgement=None,
                    checks=[],
                    positions={},
                    seen=[{"person": 0, "character": "NANDI", "sex": "female"}],
                    found=[{"character": "NANDI", "person": 0, "reason": "r"}],
                    layout={"panels": 1, "copies": [], "reason": "r"},
                    verdict="pass",
                    models=["m"],
                    prompt_tokens=1,
                    completion_tokens=1,
                )
            )
        if comic:
            cj = uuid.uuid4()
            s.add(
                JobRow(
                    id=cj,
                    project_id=pid,
                    kind=JobKind.COMIC,
                    state=JobState.DONE,
                    stage="rendering",
                    progress=100,
                )
            )
            await s.flush()
            s.add(
                ComicRow(
                    project_id=pid,
                    job_id=cj,
                    layout={"pages": []},
                    pages=["comics/p.png"],
                    pdf="comics/c.pdf",
                )
            )
    return pid


async def count(
    sessions: async_sessionmaker[AsyncSession], table: Any, owner_of: Any = None
) -> int:
    async with sessions() as s:
        return await s.scalar(select(func.count()).select_from(table)) or 0


async def test_a_settled_project_is_copied_once_with_its_frames_audits_and_comic(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    source = await finished(sessions, comic=True)
    judge = uuid.uuid4()
    first = await copy_sample(sessions, source, judge)
    again = await copy_sample(sessions, source, judge)
    assert first.copied and not again.copied and again.project_id == first.project_id
    async with sessions() as s:
        src = await s.get(ProjectRow, source)
        copy = await s.get(ProjectRow, first.project_id)
        frames = list(await s.scalars(select(FrameRow).where(FrameRow.project_id == copy.id)))  # type: ignore[union-attr]
        audits = await s.scalar(
            select(func.count())
            .select_from(FrameAuditRow)
            .where(FrameAuditRow.project_id == copy.id)  # type: ignore[union-attr]
        )
        comic = await s.get(ComicRow, first.project_id)
        copied = list(
            await s.scalars(select(FrameAuditRow).where(FrameAuditRow.project_id == copy.id))  # type: ignore[union-attr]
        )
    # The agents' answers come with each audit, so `recheck` decides the copy as the source.
    assert copied and all(
        a.seen == [{"person": 0, "character": "NANDI", "sex": "female"}]
        and a.found == [{"character": "NANDI", "person": 0, "reason": "r"}]
        and a.layout == {"panels": 1, "copies": [], "reason": "r"}
        for a in copied
    )
    assert src is not None and copy is not None
    assert (copy.owner, copy.title, copy.pdf_path, copy.plan) == (
        judge,
        src.title,
        src.pdf_path,
        src.plan,
    )
    assert copy.created_at == src.created_at  # so the sample never counts toward the day's uploads
    assert frames and all(f.state == "passed" and f.asset for f in frames)
    assert audits == len(frames)
    assert comic is not None and comic.pages == ["comics/p.png"] and comic.job_id != source
    # The source is untouched.
    async with sessions() as s:
        owned = await s.scalar(
            select(func.count()).select_from(ProjectRow).where(ProjectRow.owner == ME)
        )
    assert owned == 1


async def test_a_storyboard_still_running_is_refused_before_anything_is_written(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    source = await finished(sessions, comic=False)
    async with sessions() as s, s.begin():
        frame = (await s.scalars(select(FrameRow).where(FrameRow.project_id == source))).first()
        assert frame is not None
        frame.state, frame.asset = "auditing", None
    with pytest.raises(SeedError, match="settled"):
        await copy_sample(sessions, source, uuid.uuid4())
    assert await count(sessions, ProjectRow) == 1


async def test_main_needs_the_judges_email_and_password_and_never_prints_them(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("JUDGE_EMAIL", raising=False)
    monkeypatch.delenv("JUDGE_PASSWORD", raising=False)
    assert await main([]) == 2
    assert "JUDGE_EMAIL" in capsys.readouterr().err
