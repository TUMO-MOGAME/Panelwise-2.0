"""frame_audits.layout: the layout agent's answer, a frame in panels or one person drawn twice
(verify.md §3; T104)

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("frame_audits", sa.Column("layout", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("frame_audits", "layout")
