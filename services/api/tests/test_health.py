"""GET /api/v1/health -- the contract in TASKS.md T002."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.api.v1.health import Check, get_checks
from app.core.config import Settings
from app.main import create_app


async def ok() -> None:
    return None


def client_with(checks: dict[str, Check], timeout_s: float = 1.0) -> TestClient:
    app = create_app(Settings(health_check_timeout_s=timeout_s))
    app.dependency_overrides[get_checks] = lambda: checks
    return TestClient(app)


def test_all_checks_pass_returns_200_ok() -> None:
    res = client_with({"postgres": ok, "second": ok}).get("/api/v1/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok", "checks": {"postgres": "ok", "second": "ok"}}


def test_a_failing_check_returns_503_degraded_and_names_the_exception_type() -> None:
    async def second_down() -> None:
        raise ConnectionRefusedError("Connection refused")

    res = client_with({"postgres": ok, "second": second_down}).get("/api/v1/health")

    assert res.status_code == 503
    assert res.json() == {
        "status": "degraded",
        "checks": {"postgres": "ok", "second": "error: ConnectionRefusedError"},
    }


def test_error_messages_are_never_returned() -> None:
    async def leaky() -> None:
        raise RuntimeError("postgresql://panelwise:hunter2@db:5432/panelwise")

    res = client_with({"postgres": leaky, "second": ok}).get("/api/v1/health")

    assert "hunter2" not in res.text
    assert res.json()["checks"]["postgres"] == "error: RuntimeError"


def test_a_hanging_check_times_out_instead_of_hanging_the_endpoint() -> None:
    async def hangs() -> None:
        await asyncio.sleep(10)

    started = time.monotonic()
    res = client_with({"postgres": hangs, "second": ok}, timeout_s=0.05).get("/api/v1/health")

    assert time.monotonic() - started < 2
    assert res.status_code == 503
    assert res.json()["checks"]["postgres"] == "error: TimeoutError"


def test_checks_run_concurrently() -> None:
    async def slow() -> None:
        await asyncio.sleep(0.3)

    # The request alone is timed: building the app and its client is not the checks' time, and
    # with the suite on every core it pushed this past the bound (pytest -n auto, #165).
    client = client_with({"postgres": slow, "second": slow})
    started = time.monotonic()
    res = client.get("/api/v1/health")

    assert res.status_code == 200
    assert time.monotonic() - started < 0.55  # two 0.3 s checks in a row would take 0.6


def test_the_real_app_checks_postgres_only() -> None:
    # docs/design/deploy.md §6: Redis is gone; job state lives in Postgres.
    app = create_app(Settings(_env_file=None))  # pyright: ignore[reportCallIssue]
    with TestClient(app):  # runs the lifespan, which registers the checks
        assert set(app.state.health_checks) == {"postgres"}


@pytest.mark.parametrize(
    "given",
    [
        "postgresql://u:p@aws-0-eu-central-1.pooler.supabase.com:5432/postgres",
        "postgres://u:p@aws-0-eu-central-1.pooler.supabase.com:5432/postgres",
        "postgresql+asyncpg://u:p@aws-0-eu-central-1.pooler.supabase.com:5432/postgres",
    ],
)
def test_a_supabase_connection_string_is_used_with_the_asyncpg_driver(given: str) -> None:
    # Supabase hands out postgresql:// URLs; SQLAlchemy's async engine needs +asyncpg.
    settings = Settings(_env_file=None, database_url=given)  # pyright: ignore[reportCallIssue]
    assert settings.database_url == (
        "postgresql+asyncpg://u:p@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
    )


@pytest.mark.parametrize(
    ("given", "expected_query"),
    [
        ("postgresql://u:p@h:5432/postgres?sslmode=require", "ssl=require"),
        ("postgres://u:p@h:5432/postgres?sslmode=verify-full", "ssl=verify-full"),
        ("postgresql+asyncpg://u:p@h:5432/postgres?ssl=require", "ssl=require"),
    ],
)
def test_libpq_sslmode_becomes_asyncpgs_ssl(given: str, expected_query: str) -> None:
    # Supabase suggests ?sslmode=require; asyncpg has no sslmode and rejects it at connect time.
    settings = Settings(_env_file=None, database_url=given)  # pyright: ignore[reportCallIssue]
    assert settings.database_url == f"postgresql+asyncpg://u:p@h:5432/postgres?{expected_query}"


def test_a_password_containing_a_question_mark_survives() -> None:
    # A "?" in the password is not the start of the query (PR #13 review).
    given = "postgresql://postgres.ref:my?pass@pooler.example.com:5432/postgres?sslmode=require"
    settings = Settings(_env_file=None, database_url=given)  # pyright: ignore[reportCallIssue]
    url = make_url(settings.database_url)
    assert (url.drivername, url.password, url.host, url.port, url.database) == (
        "postgresql+asyncpg",
        "my?pass",
        "pooler.example.com",
        5432,
        "postgres",
    )
    assert dict(url.query) == {"ssl": "require"}
