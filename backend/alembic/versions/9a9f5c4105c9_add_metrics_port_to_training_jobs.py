"""add metrics_port to training_jobs

Revision ID: 9a9f5c4105c9
Revises: a3d4e5f6b7c8
Create Date: 2026-05-11 14:30:16.604178

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a9f5c4105c9"
down_revision: str | Sequence[str] | None = "a3d4e5f6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("training_jobs", sa.Column("metrics_port", sa.Integer(), nullable=True, comment="指标端口"))


def downgrade() -> None:
    op.drop_column("training_jobs", "metrics_port")
