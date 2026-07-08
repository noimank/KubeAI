"""add_annotation_task_result_drop_callback_fields

Revision ID: 8b1a2c3d4e5f
Revises: 359a38166af7
Create Date: 2026-07-08 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b1a2c3d4e5f"
down_revision: str | Sequence[str] | None = "359a38166af7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Add AnnotationTask.result (JSONB) for per-submit payload persistence,
    and drop the batch-callback machinery on AnnotationProject.
    """
    op.add_column(
        "annotation_tasks",
        sa.Column("result", postgresql.JSONB, nullable=True),
    )

    # FK must be dropped before its column.
    op.drop_constraint(
        "fk_annotation_projects_callback_version_id",
        "annotation_projects",
        type_="foreignkey",
    )
    op.drop_column("annotation_projects", "callback_at")
    op.drop_column("annotation_projects", "callback_version_id")
    op.drop_column("annotation_projects", "callback_progress")
    op.drop_column("annotation_projects", "callback_error")
    op.drop_column("annotation_projects", "callback_status")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "annotation_projects",
        sa.Column("callback_status", sa.String(length=20), server_default="pending", nullable=False),
    )
    op.add_column("annotation_projects", sa.Column("callback_error", sa.Text(), nullable=True))
    op.add_column(
        "annotation_projects",
        sa.Column("callback_progress", sa.Integer(), server_default="0", nullable=False),
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
    op.drop_column("annotation_tasks", "result")
