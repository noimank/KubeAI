"""add mlflow_enabled & tensorboard_enabled, drop metrics_port from training_jobs

Revision ID: 06d91879e72f
Revises: a1b2c3d4e5f7
Create Date: 2026-06-25 14:48:19.170529

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "06d91879e72f"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "training_jobs",
        sa.Column(
            "mlflow_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="是否启用 MLflow 实验追踪 (默认关闭, 需要可视化时在创建表单中开启)",
        ),
    )
    op.add_column(
        "training_jobs",
        sa.Column(
            "tensorboard_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="是否启用 TensorBoard 可视化 (默认关闭, 平台注入 sidecar 自动读取 tfevents)",
        ),
    )
    op.drop_column("training_jobs", "metrics_port")


def downgrade() -> None:
    op.add_column(
        "training_jobs",
        sa.Column("metrics_port", sa.Integer(), nullable=True, comment="指标端口"),
    )
    op.drop_column("training_jobs", "tensorboard_enabled")
    op.drop_column("training_jobs", "mlflow_enabled")
