"""add_source_tracking_to_training_jobs

Revision ID: 06ce71516398
Revises: 7d5e0851d014
Create Date: 2026-05-21 09:03:30.664148

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "06ce71516398"
down_revision: str | Sequence[str] | None = "7d5e0851d014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "training_jobs",
        sa.Column(
            "source",
            sa.String(length=30),
            nullable=False,
            server_default="manual",
            comment="任务来源: manual=手动创建, dev_environment=开发环境, experiment_reproduction=实验复现",
        ),
    )
    op.add_column("training_jobs", sa.Column("source_env_id", sa.Uuid(), nullable=True, comment="来源开发环境 ID"))
    op.create_foreign_key(
        "fk_training_jobs_source_env_id",
        "training_jobs",
        "dev_environments",
        ["source_env_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_training_jobs_source_env_id", "training_jobs", type_="foreignkey")
    op.drop_column("training_jobs", "source_env_id")
    op.drop_column("training_jobs", "source")
