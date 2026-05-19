"""add_annotation_callback_fields

Revision ID: 56e18b6c8cca
Revises: a8f2e3d4c5b6
Create Date: 2026-05-19 15:01:26.635932

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "56e18b6c8cca"
down_revision: str | Sequence[str] | None = "a8f2e3d4c5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "annotation_projects",
        sa.Column("callback_status", sa.String(length=20), server_default="pending", nullable=False),
    )
    op.add_column("annotation_projects", sa.Column("callback_error", sa.Text(), nullable=True))
    op.add_column(
        "annotation_projects", sa.Column("callback_progress", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("annotation_projects", sa.Column("callback_version_id", sa.Uuid(), nullable=True))
    op.add_column("annotation_projects", sa.Column("callback_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_annotation_projects_callback_version_id",
        "annotation_projects",
        "dataset_versions",
        ["callback_version_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_annotation_projects_callback_version_id", "annotation_projects", type_="foreignkey")
    op.drop_column("annotation_projects", "callback_at")
    op.drop_column("annotation_projects", "callback_version_id")
    op.drop_column("annotation_projects", "callback_progress")
    op.drop_column("annotation_projects", "callback_error")
    op.drop_column("annotation_projects", "callback_status")
