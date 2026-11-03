"""The database: one declarative base, and the engine and sessions built from Settings.

docs/design/deploy.md §6 (T009). Migrations are Alembic's (migrations/); the app never creates
tables itself.
"""

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, Text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings


class Base(DeclarativeBase):
    # The migrations' types: text, never VARCHAR, and timezone-aware timestamps (deploy.md §6).
    # tests/db/test_schema.py fails if a model and the migrations ever disagree.
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        str: Text(),
        datetime: DateTime(timezone=True),
    }


def make_engine(settings: Settings) -> AsyncEngine:
    # Lazy: building it never touches the network. Deployed, DATABASE_URL is Supabase's session
    # pooler, which keeps prepared statements working (deploy.md §6).
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def make_sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
