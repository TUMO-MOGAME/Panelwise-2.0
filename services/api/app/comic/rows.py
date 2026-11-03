"""A `comics` row: the one stored comic of a project (comic.md §6; T064). Written only by the comic
job, in the transaction that marks it done, so a reader never sees half a comic."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ComicRow(Base):
    __tablename__ = "comics"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    layout: Mapped[dict[str, Any]] = mapped_column(JSONB)  # to_json, frame_url holding a path
    pages: Mapped[list[str]] = mapped_column(ARRAY(Text()))  # comics/<sha256>.png, page order
    pdf: Mapped[str]  # comics/<sha256>.pdf
    made_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
