"""frame_audits.seen: the sex agent's answers about each matched person (verify.md §3; T095)

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("frame_audits", sa.Column("seen", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("frame_audits", "seen")
