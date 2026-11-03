"""Alembic's runner, async (deploy.md §6). The database is DATABASE_URL through Settings, or the
URL a caller passes in `config.attributes["database_url"]` (the tests' own database)."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.comic.rows
import app.frames.model
import app.jobs.model
import app.limits.usage
import app.projects.model
from app.core.config import Settings
from app.db import Base

config = context.config
if config.config_file_name is not None and not config.attributes.get("database_url"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
_ = (app.jobs.model, app.frames.model)


def run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def main() -> None:
    url = config.attributes.get("database_url") or Settings().database_url
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        await connection.run_sync(run)
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline migrations are not used: run against a database")
asyncio.run(main())
