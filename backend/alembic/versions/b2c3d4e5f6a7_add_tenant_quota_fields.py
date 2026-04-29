"""add_tenant_quota_fields

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-29 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("gpu_limit", sa.Integer(), server_default="0", nullable=False))
    op.add_column("tenants", sa.Column("cpu_limit", sa.String(20), server_default="4", nullable=False))
    op.add_column("tenants", sa.Column("memory_limit", sa.String(20), server_default="8Gi", nullable=False))
    op.add_column("tenants", sa.Column("storage_limit", sa.String(20), server_default="10Gi", nullable=False))


def downgrade() -> None:
    op.drop_column("tenants", "storage_limit")
    op.drop_column("tenants", "memory_limit")
    op.drop_column("tenants", "cpu_limit")
    op.drop_column("tenants", "gpu_limit")
