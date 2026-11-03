"""projects and jobs, with row-level security on and no policies (deploy.md §6, T009)

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from migrations.helpers import lock_down

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # clock_timestamp(), not now(): now() is the transaction's start, so two rows inserted in one
    # transaction would tie, and "newest first" would be arbitrary.
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("pdf_path", sa.Text(), nullable=False),
        sa.Column("screenplay", JSONB(), nullable=True),
        sa.Column("extraction", JSONB(), nullable=True),
        sa.Column("plan", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
    )
    op.create_index("projects_owner_created", "projects", ["owner", sa.text("created_at DESC")])
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint("kind IN ('storyboard', 'frame_attempt')", name="jobs_kind"),
        sa.CheckConstraint("state IN ('queued', 'running', 'done', 'failed')", name="jobs_state"),
        sa.CheckConstraint(
            "stage IS NULL OR stage IN ('parsing', 'extracting', 'planning', 'rendering')",
            name="jobs_stage",
        ),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="jobs_progress"),
    )
    op.create_index("jobs_project_created", "jobs", ["project_id", sa.text("created_at DESC")])
    # Alembic's own table too: it lives in public, where Supabase's Data API can see it.
    for table in ("projects", "jobs", "alembic_version"):
        lock_down(table)


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("projects")
