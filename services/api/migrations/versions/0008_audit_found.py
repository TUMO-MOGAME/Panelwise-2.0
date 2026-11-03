"""frame_audits.found: the presence agent's answers about each drawn character (verify.md §3;
T099)

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("frame_audits", sa.Column("found", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("frame_audits", "found")
