"""add stopped_reason to dev_environments

Revision ID: 7d5e0851d014
Revises: e1b8a0ab42b2
Create Date: 2026-05-20 17:58:19.744375

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d5e0851d014"
down_revision: str | Sequence[str] | None = "e1b8a0ab42b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dev_environments",
        sa.Column(
            "stopped_reason",
            sa.String(length=20),
            nullable=True,
            comment="停止原因: manual=手动停止, idle_timeout=空闲超时自动停止",
        ),
    )


def downgrade() -> None:
    op.drop_column("dev_environments", "stopped_reason")
