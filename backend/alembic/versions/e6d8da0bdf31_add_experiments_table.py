"""add experiments table

Revision ID: e6d8da0bdf31
Revises: 4d727b7fb1c7
Create Date: 2026-05-12 15:07:27.969275

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6d8da0bdf31"
down_revision: str | Sequence[str] | None = "4d727b7fb1c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("training_job_id", sa.Uuid(), nullable=False),
        sa.Column("mlflow_experiment_id", sa.String(length=100), nullable=True),
        sa.Column("mlflow_run_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["training_job_id"], ["training_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_experiments_tenant_id"), "experiments", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_experiments_training_job_id"), "experiments", ["training_job_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_experiments_training_job_id"), table_name="experiments")
    op.drop_index(op.f("ix_experiments_tenant_id"), table_name="experiments")
    op.drop_table("experiments")
