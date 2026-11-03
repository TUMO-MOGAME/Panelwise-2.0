"""The API's startup sweep (web.md §4.1, §6 *API internals*; T009)."""

import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.jobs import RESTARTED, JobKind, JobRow, JobState
from app.main import create_app
from app.projects.repo import create_upload

pytestmark = pytest.mark.db


async def test_a_job_left_running_reads_failed_once_the_api_starts(
    sessions: async_sessionmaker[AsyncSession], migrated: str
) -> None:
    owner, pid = uuid.uuid4(), uuid.uuid4()
    async with sessions() as s:
        _, queued = await create_upload(
            s, project_id=pid, owner=owner, title="t", pdf_path=f"scripts/{owner}/{pid}.pdf"
        )
        running = JobRow(
            id=uuid.uuid4(),
            project_id=pid,
            kind=JobKind.STORYBOARD,
            state=JobState.RUNNING,
            progress=5,
        )
        s.add(running)
        await s.commit()

    with TestClient(create_app(Settings(database_url=migrated))):
        pass  # the lifespan ran: startup, then shutdown

    async with sessions() as s:
        rows = {j.id: (j.state, j.error) for j in (await s.execute(select(JobRow))).scalars()}
    assert rows == {
        queued.id: (JobState.FAILED, RESTARTED),
        running.id: (JobState.FAILED, RESTARTED),
    }


def test_an_unreachable_database_does_not_stop_the_api_starting(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Port 9 (discard) refuses: the sweep logs and the API still serves; health reports it.
    settings = Settings(database_url="postgresql://u:p@127.0.0.1:9/nothing_test")
    with caplog.at_level(logging.WARNING), TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health").status_code == 503
    assert any("restart sweep" in r.getMessage() for r in caplog.records)
