"""unify inference (drop service_type/model binding/canary) + add image category

Revision ID: b2f6a1c80d3e
Revises: a1e5f2c98b4d
Create Date: 2026-06-29 18:00:00.000000

推理服务彻底统一: 不再区分 model/custom, 解绑模型版本, 移除金丝雀; 推理 = 跑运行时
镜像的 Deployment + KEDA, 模型/代码可打进镜像或放挂载的共享卷. 同时给 Image 加
category 字段 (training/inference/other), 训练只取 training, 推理只取 inference.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2f6a1c80d3e"
down_revision: str | Sequence[str] | None = "a1e5f2c98b4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Image.category (NOT NULL, 回填 training). 同时调整唯一索引: 类别下名称不重复.
    op.add_column("images", sa.Column("category", sa.String(length=20), nullable=False, server_default="training"))
    op.execute("UPDATE images SET category = 'training'")
    op.drop_constraint("uq_image_tenant_name_tag", "images", type_="unique")
    op.create_unique_constraint("uq_image_tenant_category_name_tag", "images", ["tenant_id", "category", "name", "tag"])

    # 2. inference_services: 移除金丝雀 (canary_model_version_id FK 有名, 按名删).
    op.drop_constraint("fk_inference_services_canary_model_version_id", "inference_services", type_="foreignkey")
    op.drop_column("inference_services", "canary_model_version_id")
    op.drop_column("inference_services", "canary_traffic_percent")
    op.drop_column("inference_services", "canary_status")

    # 3. inference_services: 移除 service_type.
    op.drop_column("inference_services", "service_type")


def downgrade() -> None:
    # 逆序恢复 (尽力而为, 不复活业务数据).
    op.add_column(
        "inference_services", sa.Column("service_type", sa.String(length=20), nullable=False, server_default="model")
    )

    op.add_column(
        "inference_services", sa.Column("canary_status", sa.String(length=20), nullable=False, server_default="none")
    )
    op.add_column("inference_services", sa.Column("canary_traffic_percent", sa.Integer(), nullable=True))
    op.add_column("inference_services", sa.Column("canary_model_version_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_inference_services_canary_model_version_id",
        "inference_services",
        "model_versions",
        ["canary_model_version_id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("uq_image_tenant_category_name_tag", "images", type_="unique")
    op.drop_column("images", "category")
    op.create_unique_constraint("uq_image_tenant_name_tag", "images", ["tenant_id", "name", "tag"])
