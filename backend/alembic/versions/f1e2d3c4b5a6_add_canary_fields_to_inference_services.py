"""add_canary_fields_to_inference_services

Revision ID: f1e2d3c4b5a6
Revises: dd31183924b3
Create Date: 2026-05-15 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1e2d3c4b5a6"
down_revision: str | Sequence[str] | None = "dd31183924b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inference_services",
        sa.Column(
            "canary_model_version_id",
            sa.UUID(),
            nullable=True,
            comment="金丝雀模型版本 ID",
        ),
    )
    op.create_foreign_key(
        "fk_inference_services_canary_model_version_id",
        "inference_services",
        "model_versions",
        ["canary_model_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "inference_services",
        sa.Column(
            "canary_traffic_percent",
            sa.Integer(),
            nullable=True,
            comment="金丝雀流量百分比 (0-100)",
        ),
    )
    op.add_column(
        "inference_services",
        sa.Column(
            "canary_kserve_name",
            sa.String(length=128),
            nullable=True,
            comment="金丝雀 InferenceService K8s 名称",
        ),
    )
    op.add_column(
        "inference_services",
        sa.Column(
            "canary_status",
            sa.String(length=20),
            nullable=False,
            server_default="none",
            comment="金丝雀状态: none/deploying/running/failed",
        ),
    )


def downgrade() -> None:
    op.drop_column("inference_services", "canary_status")
    op.drop_column("inference_services", "canary_kserve_name")
    op.drop_column("inference_services", "canary_traffic_percent")
    op.drop_constraint(
        "fk_inference_services_canary_model_version_id",
        "inference_services",
        type_="foreignkey",
    )
    op.drop_column("inference_services", "canary_model_version_id")
