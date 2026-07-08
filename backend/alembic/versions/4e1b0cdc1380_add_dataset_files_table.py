"""add dataset_files table

Revision ID: 4e1b0cdc1380
Revises: 8b1a2c3d4e5f
Create Date: 2026-07-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4e1b0cdc1380"
down_revision: str | Sequence[str] | None = "8b1a2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dataset_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["dataset_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "relative_path", name="uq_dataset_file_version_path"),
    )
    op.create_index("ix_dataset_files_tenant", "dataset_files", ["tenant_id"])
    op.create_index("ix_dataset_files_dataset", "dataset_files", ["dataset_id"])
    op.create_index("ix_dataset_files_version_name", "dataset_files", ["version_id", "file_name"])
    op.create_index("ix_dataset_files_version_uploaded_at", "dataset_files", ["version_id", "uploaded_at"])


def downgrade() -> None:
    op.drop_index("ix_dataset_files_version_uploaded_at", table_name="dataset_files")
    op.drop_index("ix_dataset_files_version_name", table_name="dataset_files")
    op.drop_index("ix_dataset_files_dataset", table_name="dataset_files")
    op.drop_index("ix_dataset_files_tenant", table_name="dataset_files")
    op.drop_table("dataset_files")
