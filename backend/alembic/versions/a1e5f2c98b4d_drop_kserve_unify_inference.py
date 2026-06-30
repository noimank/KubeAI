"""drop kserve columns, mark legacy model services failed

Revision ID: a1e5f2c98b4d
Revises: 06d91879e72f
Create Date: 2026-06-29 12:00:00.000000

KServe 被移除: 推理服务全部走自定义运行时 (裸 Deployment + Service + KEDA).
本迁移删除 KServe 专属列 (kserve_name / canary_kserve_name), 并把引用已删 KServe
InferenceService 的存量 model 服务标记为 failed, 要求运营者在新的 Deployment
路径上重新部署. 金丝雀字段 (canary_model_version_id / canary_traffic_percent /
canary_status) 保留但置为惰性值 (本轮移除金丝雀功能, 后续迭代再恢复).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1e5f2c98b4d"
down_revision: str | Sequence[str] | None = "06d91879e72f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 存量 RUNNING/DEPLOYING/PENDING 的 model 服务引用的 KServe InferenceService
    # 即将不存在 (KServe 整体卸载), 标记 failed 要求重新部署. 先执行, 再删列, 顺序无关.
    op.execute(
        "UPDATE inference_services "
        "SET status = 'failed', error_message = 'KServe 已移除, 请重新部署该推理服务' "
        "WHERE status IN ('running', 'deploying', 'pending') AND service_type = 'model'"
    )
    # 防御性 backfill (c7d8e9f0a1b2 后 service_type 应已非 NULL).
    op.execute("UPDATE inference_services SET service_type = 'model' WHERE service_type IS NULL")
    # 金丝雀字段惰性化 (列保留, 本轮移除金丝雀功能).
    op.execute(
        "UPDATE inference_services "
        "SET canary_status = 'none', canary_traffic_percent = NULL, canary_model_version_id = NULL"
    )
    # 删除 KServe 专属列.
    op.drop_column("inference_services", "kserve_name")
    op.drop_column("inference_services", "canary_kserve_name")


def downgrade() -> None:
    # 尽力而为: 恢复列结构, 不复活 KServe 数据 / 状态.
    op.add_column(
        "inference_services",
        sa.Column("canary_kserve_name", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "inference_services",
        sa.Column("kserve_name", sa.String(length=100), nullable=True),
    )
