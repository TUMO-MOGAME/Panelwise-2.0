"""frames: one row per shot in verify's state machine (web.md §6, T047)

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.helpers import lock_down

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "frames",
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("scene_index", sa.Integer(), primary_key=True),
        sa.Column("shot_number", sa.Integer(), primary_key=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column(
            "job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("asset", sa.Text(), nullable=True),
        sa.Column("withheld_check", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint(
            "state IN ('rendering', 'auditing', 'passed', 'warned', 'withheld', 'failed')",
            name="frames_state",
        ),
        sa.CheckConstraint("attempt >= 1", name="frames_attempt"),
        sa.CheckConstraint("asset IS NULL OR state IN ('passed', 'warned')", name="frames_asset"),
    )
    lock_down("frames")


def downgrade() -> None:
    op.drop_table("frames")
