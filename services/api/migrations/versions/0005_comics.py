"""comics: one stored comic per project; comic jobs; frame_audits.target (comic.md §4a, §6; T064)

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from migrations.helpers import lock_down

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("jobs_kind", "jobs", type_="check")
    op.create_check_constraint(
        "jobs_kind", "jobs", "kind IN ('storyboard', 'frame_attempt', 'comic')"
    )

    # Which frame an audit row is about: the storyboard's 1280 x 720 frame or a comic panel at its
    # rect. Rows before this migration are the storyboard's.
    op.add_column(
        "frame_audits",
        sa.Column("target", sa.Text(), nullable=False, server_default=sa.text("'storyboard'")),
    )
    op.create_check_constraint(
        "frame_audits_target", "frame_audits", "target IN ('storyboard', 'comic')"
    )
    op.drop_constraint("frame_audits_frame", "frame_audits", type_="unique")
    op.create_unique_constraint(
        "frame_audits_frame",
        "frame_audits",
        ["project_id", "target", "scene_index", "shot_number", "attempt"],
    )

    op.create_table(
        "comics",
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("layout", JSONB(), nullable=False),
        sa.Column("pages", ARRAY(sa.Text()), nullable=False),
        sa.Column("pdf", sa.Text(), nullable=False),
        sa.Column(
            "made_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
    )
    lock_down("comics")


def downgrade() -> None:
    # Comic jobs cascade to their comics and their audit rows; then nothing breaks the old rules.
    op.execute("DELETE FROM jobs WHERE kind = 'comic'")
    op.execute("DELETE FROM frame_audits WHERE target = 'comic'")
    op.drop_table("comics")
    op.drop_constraint("frame_audits_frame", "frame_audits", type_="unique")
    op.create_unique_constraint(
        "frame_audits_frame",
        "frame_audits",
        ["project_id", "scene_index", "shot_number", "attempt"],
    )
    op.drop_constraint("frame_audits_target", "frame_audits", type_="check")
    op.drop_column("frame_audits", "target")
    op.drop_constraint("jobs_kind", "jobs", type_="check")
    op.create_check_constraint("jobs_kind", "jobs", "kind IN ('storyboard', 'frame_attempt')")
