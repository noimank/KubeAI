"""add model version deploy config

模型版本新增 deploy_config (JSON, 可空): 上传/注册时可选沉淀推理部署参数
(候选镜像列表 + 端口/命令/参数/环境变量/资源建议), 部署为推理服务时预填.

Revision ID: c7f8a9b0d1e2
Revises: b5e6f7a8c9d0
Create Date: 2026-09-15 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7f8a9b0d1e2"
down_revision: str | Sequence[str] | None = "b5e6f7a8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("model_versions", sa.Column("deploy_config", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("model_versions", "deploy_config")
