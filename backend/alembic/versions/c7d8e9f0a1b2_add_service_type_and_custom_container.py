"""add service_type and custom container fields to inference_services

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-05-27 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "b6c7d8e9f0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inference_services",
        sa.Column("service_type", sa.String(20), nullable=False, server_default="model"),
    )
    op.alter_column("inference_services", "model_version_id", existing_type=sa.UUID(), nullable=True)
    op.add_column(
        "inference_services",
        sa.Column("container_port", sa.Integer(), nullable=True),
    )
    op.add_column(
        "inference_services",
        sa.Column("command", sa.Text(), nullable=True),
    )
    op.add_column(
        "inference_services",
        sa.Column("args", sa.Text(), nullable=True),
    )
    op.add_column(
        "inference_services",
        sa.Column("k8s_deployment_name", sa.String(100), nullable=True),
    )
    op.add_column(
        "inference_services",
        sa.Column("k8s_service_name", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("inference_services", "k8s_service_name")
    op.drop_column("inference_services", "k8s_deployment_name")
    op.drop_column("inference_services", "args")
    op.drop_column("inference_services", "command")
    op.drop_column("inference_services", "container_port")
    op.alter_column("inference_services", "model_version_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("inference_services", "service_type")
