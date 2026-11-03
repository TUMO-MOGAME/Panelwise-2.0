"""frame_audits: one row per audited attempt, passed or not (verify.md §6, T021)

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from migrations.helpers import lock_down

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "frame_audits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("scene_index", sa.Integer(), nullable=False),
        sa.Column("shot_number", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("frame_asset", sa.Text(), nullable=False),
        sa.Column("description", JSONB(), nullable=True),
        sa.Column("judgement", JSONB(), nullable=True),
        sa.Column("checks", JSONB(), nullable=False),
        sa.Column("positions", JSONB(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("models", JSONB(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint(
            "verdict IN ('pass', 'warn', 'fail', 'error')", name="frame_audits_verdict"
        ),
        sa.CheckConstraint("attempt >= 1", name="frame_audits_attempt"),
        sa.UniqueConstraint(
            "project_id", "scene_index", "shot_number", "attempt", name="frame_audits_frame"
        ),
    )
    lock_down("frame_audits")


def downgrade() -> None:
    op.drop_table("frame_audits")
