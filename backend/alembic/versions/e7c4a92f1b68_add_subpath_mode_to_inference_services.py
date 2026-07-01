"""add_subpath_mode_to_inference_services

Revision ID: e7c4a92f1b68
Revises: b2f6a1c80d3e
Create Date: 2026-07-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7c4a92f1b68"
down_revision: str | Sequence[str] | None = "b2f6a1c80d3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inference_services",
        sa.Column(
            "subpath_mode",
            sa.String(length=20),
            nullable=False,
            server_default="rewrite",
            comment="子路径模式: rewrite/native",
        ),
    )


def downgrade() -> None:
    op.drop_column("inference_services", "subpath_mode")
