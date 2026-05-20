"""add mounted_datasets to dev_environments

Revision ID: e1b8a0ab42b2
Revises: eef515c83d81
Create Date: 2026-05-20 12:27:32.601636

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1b8a0ab42b2"
down_revision: str | Sequence[str] | None = "eef515c83d81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dev_environments",
        sa.Column(
            "mounted_datasets",
            sa.JSON(),
            nullable=True,
            comment="挂载的数据集列表 [{dataset_id, dataset_name, version_id, version_number, pvc_name, mount_path}]",
        ),
    )


def downgrade() -> None:
    op.drop_column("dev_environments", "mounted_datasets")
