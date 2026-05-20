"""add_kubeai_object_name_to_annotation_tasks

Revision ID: 7b3c4d5e6f7a
Revises: 56e18b6c8cca
Create Date: 2026-05-20 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b3c4d5e6f7a"
down_revision: str | Sequence[str] | None = "56e18b6c8cca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add kubeai_object_name column with backfill from JSONB data."""
    op.add_column(
        "annotation_tasks",
        sa.Column("kubeai_object_name", sa.String(length=1024), nullable=True),
    )
    op.execute(
        "UPDATE annotation_tasks SET kubeai_object_name = data->>'kubeai_object_name' WHERE kubeai_object_name IS NULL"
    )
    op.alter_column("annotation_tasks", "kubeai_object_name", nullable=False)
    op.create_unique_constraint(
        "uq_annotation_task_project_object",
        "annotation_tasks",
        ["project_id", "kubeai_object_name"],
    )


def downgrade() -> None:
    """Remove kubeai_object_name column."""
    op.drop_constraint("uq_annotation_task_project_object", "annotation_tasks", type_="unique")
    op.drop_column("annotation_tasks", "kubeai_object_name")
