"""llm_usage: Token Factory tokens per calendar month, the hosted demo's budget (limits.md; T069)

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.helpers import lock_down

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("month", sa.Date(), primary_key=True),
        sa.Column("tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
    )
    lock_down("llm_usage")


def downgrade() -> None:
    op.drop_table("llm_usage")
