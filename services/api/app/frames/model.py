"""A `frames` row: one shot's place in verify's state machine (web.md §3, §6; T047 creates and
reads it, T021 writes it). The only source of `FrameView`."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

FRAME_STATES = ("rendering", "auditing", "passed", "warned", "withheld", "failed")
ACCEPTED = ("passed", "warned")  # the only states that may reference an image


class AuditTarget(StrEnum):
    """Which frame an audit row is about (verify.md §6): the storyboard's, or a comic panel."""

    STORYBOARD = "storyboard"
    COMIC = "comic"


class FrameRow(Base):
    __tablename__ = "frames"
    __table_args__ = (
        CheckConstraint(
            "state IN ('rendering', 'auditing', 'passed', 'warned', 'withheld', 'failed')",
            name="frames_state",
        ),
        CheckConstraint("attempt >= 1", name="frames_attempt"),
        # A withheld frame's file is never referenced (web.md §3).
        CheckConstraint("asset IS NULL OR state IN ('passed', 'warned')", name="frames_asset"),
        # Why a failed frame failed (T021): the renderer or the restart sweep; only failed has one.
        CheckConstraint(
            "failure IS NULL OR (state = 'failed' AND failure IN ('render', 'restart'))",
            name="frames_failure",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    scene_index: Mapped[int] = mapped_column(primary_key=True)
    shot_number: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str]
    attempt: Mapped[int]
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    asset: Mapped[str | None] = mapped_column(default=None)
    withheld_check: Mapped[str | None] = mapped_column(default=None)
    failure: Mapped[str | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.clock_timestamp(), onupdate=func.clock_timestamp()
    )


class FrameAuditRow(Base):
    """One audited attempt (verify.md §6, T021): every attempt, passed or not. `frame_asset` is the
    attempt's Storage path and never reaches the web; only a frames row's accepted asset does."""

    __tablename__ = "frame_audits"
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('pass', 'warn', 'fail', 'error')", name="frame_audits_verdict"
        ),
        CheckConstraint("attempt >= 1", name="frame_audits_attempt"),
        CheckConstraint("target IN ('storyboard', 'comic')", name="frame_audits_target"),
        # one row per attempt of a frame; also the index a frame's attempts are read by
        UniqueConstraint(
            "project_id",
            "target",
            "scene_index",
            "shot_number",
            "attempt",
            name="frame_audits_frame",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    target: Mapped[str] = mapped_column(
        default=AuditTarget.STORYBOARD.value, server_default=text("'storyboard'")
    )
    scene_index: Mapped[int]
    shot_number: Mapped[int]
    attempt: Mapped[int]
    seed: Mapped[int] = mapped_column(BigInteger())
    frame_asset: Mapped[str]
    description: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    judgement: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    positions: Mapped[dict[str, str]] = mapped_column(JSONB)
    # T095: the sex agent's answers, [{person, character, sex}]; None on rows before 0007.
    seen: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, default=None)
    # T099: the presence agent's answers, [{character, person, reason}]; None before 0008.
    found: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, default=None)
    # T104: the layout agent's answer, {panels, copies, reason}; None if not asked or before 0009.
    layout: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    # T097: the head agent's kept boxes, [{person, character, box: [x0, y0, x1, y1]}]; None when
    # not asked (storyboard frames, thrown-away attempts) or before 0010.
    heads: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, default=None)
    verdict: Mapped[str]
    models: Mapped[list[str]] = mapped_column(JSONB)
    prompt_tokens: Mapped[int]
    completion_tokens: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
