"""frame_audits.heads: the head agent's boxes on a comic panel's accepted frame (verify.md §3;
T097)

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("frame_audits", sa.Column("heads", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("frame_audits", "heads")
