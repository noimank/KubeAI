"""add worker_count to training_jobs

Revision ID: a3d4e5f6b7c8
Revises: fe1aaeb21ed8
Create Date: 2026-05-08 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3d4e5f6b7c8"
down_revision: str | Sequence[str] | None = "fe1aaeb21ed8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "training_jobs",
        sa.Column("worker_count", sa.Integer(), nullable=False, server_default="1", comment="Worker 数量"),
    )


def downgrade() -> None:
    op.drop_column("training_jobs", "worker_count")
