"""A job row: one run of work for a project, so progress survives a restart (deploy.md §3, §5)."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# clock_timestamp(), not now(): now() is the transaction's start, so rows inserted in one
# transaction would tie and "newest first" would be arbitrary (migration 0001).

# web.md §4.1, verbatim: what a job left running by a restart says.
RESTARTED = "The server restarted while this ran. Upload the script again."


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobKind(StrEnum):
    STORYBOARD = "storyboard"  # the upload's job
    FRAME_ATTEMPT = "frame_attempt"  # one "Try another render" (T021)
    COMIC = "comic"  # making the project's comic (comic.md §4a, T064)


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('storyboard', 'frame_attempt', 'comic')", name="jobs_kind"),
        CheckConstraint("state IN ('queued', 'running', 'done', 'failed')", name="jobs_state"),
        CheckConstraint(
            "stage IS NULL OR stage IN ('parsing', 'extracting', 'planning', 'rendering')",
            name="jobs_stage",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="jobs_progress"),
        Index("jobs_project_created", "project_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    kind: Mapped[str]
    state: Mapped[str]
    stage: Mapped[str | None] = mapped_column(default=None)
    progress: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.clock_timestamp(), onupdate=func.clock_timestamp()
    )
