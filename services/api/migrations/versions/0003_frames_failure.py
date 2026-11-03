"""frames.failure: why a failed frame failed, the renderer or the restart sweep (web.md §6, T021)

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("frames", sa.Column("failure", sa.Text(), nullable=True))
    op.create_check_constraint(
        "frames_failure",
        "frames",
        "failure IS NULL OR (state = 'failed' AND failure IN ('render', 'restart'))",
    )


def downgrade() -> None:
    op.drop_constraint("frames_failure", "frames", type_="check")
    op.drop_column("frames", "failure")
