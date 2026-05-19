"""create annotation_tasks table

Revision ID: a8f2e3d4c5b6
Revises: 628da21e70dc
Create Date: 2026-05-19 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8f2e3d4c5b6"
down_revision: str | Sequence[str] | None = "628da21e70dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "annotation_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("label_studio_task_id", sa.Integer(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("assigned_to", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["annotation_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_annotation_tasks_tenant_id"), "annotation_tasks", ["tenant_id"], unique=False)
    op.create_index("idx_annotation_tasks_project", "annotation_tasks", ["project_id"])
    op.create_index("idx_annotation_tasks_assigned_to", "annotation_tasks", ["assigned_to"])
    op.create_index("idx_annotation_tasks_tenant_status", "annotation_tasks", ["tenant_id", "status"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_annotation_tasks_tenant_status", table_name="annotation_tasks")
    op.drop_index("idx_annotation_tasks_assigned_to", table_name="annotation_tasks")
    op.drop_index("idx_annotation_tasks_project", table_name="annotation_tasks")
    op.drop_index(op.f("ix_annotation_tasks_tenant_id"), table_name="annotation_tasks")
    op.drop_table("annotation_tasks")
