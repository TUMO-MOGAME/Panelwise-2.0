"""A project row: one uploaded screenplay and each stage's result (web.md §3, deploy.md §6)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Index, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProjectRow(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("projects_owner_created", "owner", text("created_at DESC")),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    owner: Mapped[uuid.UUID]  # the Supabase Auth user id; not a foreign key (deploy.md §6)
    title: Mapped[str]
    pdf_path: Mapped[str]  # scripts/{owner}/{id}.pdf in Supabase Storage
    # Each stage's result, written by T046 with the job's advance (web.md §3).
    screenplay: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
