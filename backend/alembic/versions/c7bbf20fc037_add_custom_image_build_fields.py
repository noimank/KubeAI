"""add custom image build fields

Revision ID: c7bbf20fc037
Revises: 6fcbd81cac10
Create Date: 2026-05-06 15:15:23.131616

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7bbf20fc037"
down_revision: str | Sequence[str] | None = "6fcbd81cac10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "images",
        sa.Column("tenant_id", sa.Uuid(), nullable=True, comment="tenant id, null for platform-level preset images"),
    )
    op.add_column(
        "images",
        sa.Column(
            "build_status",
            sa.String(length=20),
            nullable=True,
            comment="build status: pending/building/pushing/succeeded/failed, null for preset images",
        ),
    )
    op.add_column(
        "images",
        sa.Column("dockerfile", sa.Text(), nullable=True, comment="dockerfile content, only for custom images"),
    )
    op.add_column(
        "images",
        sa.Column(
            "build_job_name", sa.String(length=100), nullable=True, comment="k8s job name for tracking build status"
        ),
    )
    op.create_index(op.f("ix_images_tenant_id"), "images", ["tenant_id"], unique=False)
    op.create_foreign_key(None, "images", "tenants", ["tenant_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(None, "images", type_="foreignkey")
    op.drop_index(op.f("ix_images_tenant_id"), table_name="images")
    op.drop_column("images", "build_job_name")
    op.drop_column("images", "dockerfile")
    op.drop_column("images", "build_status")
    op.drop_column("images", "tenant_id")
