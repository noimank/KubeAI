"""add_auto_scaling_fields_to_inference_services

Revision ID: dd31183924b3
Revises: 2a8616f12699
Create Date: 2026-05-15 15:05:52.207337

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dd31183924b3"
down_revision: str | Sequence[str] | None = "2a8616f12699"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inference_services",
        sa.Column(
            "scaling_mode", sa.String(length=20), nullable=False, server_default="fixed", comment="伸缩模式: fixed/auto"
        ),
    )
    op.add_column(
        "inference_services",
        sa.Column("target_metric_type", sa.String(length=20), nullable=True, comment="目标指标类型: concurrency/cpu"),
    )
    op.add_column(
        "inference_services", sa.Column("target_metric_value", sa.Integer(), nullable=True, comment="目标指标阈值")
    )
    op.add_column(
        "inference_services",
        sa.Column("cooldown_period", sa.Integer(), nullable=False, server_default="300", comment="冷却时间(秒)"),
    )
    op.add_column(
        "inference_services",
        sa.Column("polling_interval", sa.Integer(), nullable=False, server_default="30", comment="轮询间隔(秒)"),
    )


def downgrade() -> None:
    op.drop_column("inference_services", "polling_interval")
    op.drop_column("inference_services", "cooldown_period")
    op.drop_column("inference_services", "target_metric_value")
    op.drop_column("inference_services", "target_metric_type")
    op.drop_column("inference_services", "scaling_mode")
