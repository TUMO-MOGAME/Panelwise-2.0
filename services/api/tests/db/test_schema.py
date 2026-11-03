"""Migration 0001: the tables, their constraints and row-level security (deploy.md §6, T009)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.db


async def columns(session: AsyncSession, table: str) -> dict[str, tuple[str, bool]]:
    rows = await session.execute(
        text(
            "SELECT column_name, data_type, is_nullable = 'YES' FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table},
    )
    return {name: (kind, nullable) for name, kind, nullable in rows}


async def test_the_tables_have_the_designed_columns(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as s:
        assert await columns(s, "projects") == {
            "id": ("uuid", False),
            "owner": ("uuid", False),
            "title": ("text", False),
            "pdf_path": ("text", False),
            "screenplay": ("jsonb", True),
            "extraction": ("jsonb", True),
            "plan": ("jsonb", True),
            "created_at": ("timestamp with time zone", False),
        }
        assert await columns(s, "jobs") == {
            "id": ("uuid", False),
            "project_id": ("uuid", False),
            "kind": ("text", False),
            "state": ("text", False),
            "stage": ("text", True),
            "progress": ("integer", False),
            "error": ("text", True),
            "created_at": ("timestamp with time zone", False),
            "updated_at": ("timestamp with time zone", False),
        }


async def test_row_level_security_is_on_for_every_table(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as s:
        rows = await s.execute(
            text(
                "SELECT relname, relrowsecurity FROM pg_class WHERE relname IN ('projects', 'jobs')"
            )
        )
        assert dict(rows.all()) == {"projects": True, "jobs": True}
        policies = await s.execute(text("SELECT count(*) FROM pg_policies"))
        assert policies.scalar_one() == 0


async def insert_project(s: AsyncSession) -> uuid.UUID:
    pid = uuid.uuid4()
    await s.execute(
        text("INSERT INTO projects (id, owner, title, pdf_path) VALUES (:i, :o, 't', 'p')"),
        {"i": pid, "o": uuid.uuid4()},
    )
    return pid


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("kind", "'thumbnail'"),
        ("state", "'paused'"),
        ("stage", "'printing'"),
        ("progress", "101"),
        ("progress", "-1"),
    ],
)
async def test_the_database_refuses_a_bad_job(
    sessions: async_sessionmaker[AsyncSession], column: str, value: str
) -> None:
    values = {"kind": "'storyboard'", "state": "'queued'", "stage": "NULL", "progress": "0"}
    values[column] = value
    async with sessions() as s:
        pid = await insert_project(s)
        with pytest.raises(IntegrityError):
            await s.execute(
                text(
                    "INSERT INTO jobs (id, project_id, kind, state, stage, progress) VALUES "
                    f"(:i, :p, {values['kind']}, {values['state']}, {values['stage']}, "
                    f"{values['progress']})"
                ),
                {"i": uuid.uuid4(), "p": pid},
            )


async def test_a_job_needs_its_project_and_goes_with_it(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as s:
        with pytest.raises(IntegrityError):
            await s.execute(
                text(
                    "INSERT INTO jobs (id, project_id, kind, state) VALUES "
                    "(:i, :p, 'storyboard', 'queued')"
                ),
                {"i": uuid.uuid4(), "p": uuid.uuid4()},
            )
    async with sessions() as s:
        pid = await insert_project(s)
        await s.execute(
            text(
                "INSERT INTO jobs (id, project_id, kind, state) VALUES "
                "(:i, :p, 'storyboard', 'queued')"
            ),
            {"i": uuid.uuid4(), "p": pid},
        )
        await s.execute(text("DELETE FROM projects WHERE id = :p"), {"p": pid})
        assert (await s.execute(text("SELECT count(*) FROM jobs"))).scalar_one() == 0


async def test_every_public_table_has_row_level_security(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    # Alembic's own alembic_version included: Supabase exposes every public table (deploy.md §6).
    async with sessions() as s:
        rows = await s.execute(
            text(
                "SELECT c.relname, c.relrowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r'"
            )
        )
        tables = dict(rows.all())
    assert set(tables) == {
        "projects",
        "jobs",
        "frames",
        "frame_audits",
        "comics",
        "llm_usage",
        "alembic_version",
    }
    assert all(tables.values()), tables


def test_the_fixture_refuses_a_database_not_named_test(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.conftest import database_url

    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://u:p@db.example.com:5432/postgres")
    with pytest.raises(pytest.fail.Exception, match="_test"):
        database_url()


def test_the_models_match_the_migrations(migrated: str) -> None:
    # Drift guard: autogenerate against the migrated database must find nothing to change.
    import asyncio

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.comic.rows import ComicRow
    from app.db import Base
    from app.frames.model import FrameRow
    from app.jobs.model import JobRow
    from app.limits.usage import LlmUsageRow
    from app.projects.model import ProjectRow

    names = {JobRow.__tablename__, ProjectRow.__tablename__, FrameRow.__tablename__}
    names |= {ComicRow.__tablename__, LlmUsageRow.__tablename__}
    assert names <= set(Base.metadata.tables)

    async def diff() -> list[object]:
        engine = create_async_engine(migrated)
        async with engine.connect() as conn:
            changes = await conn.run_sync(
                lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata)
            )
        await engine.dispose()
        return list(changes)

    assert asyncio.run(diff()) == []
