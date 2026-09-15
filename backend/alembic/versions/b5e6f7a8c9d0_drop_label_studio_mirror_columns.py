"""drop label studio mirror columns

标注链路已完全自研 (前端自渲染 + 标注结果落地数据集 annotations/ 目录),
LabelStudio 服务器下线, 删除其镜像字段:
- annotation_projects.label_studio_project_id
- annotation_tasks.label_studio_task_id

Revision ID: b5e6f7a8c9d0
Revises: d4e5f6a7b8c1
Create Date: 2026-09-15 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b5e6f7a8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("annotation_tasks", "label_studio_task_id")
    op.drop_column("annotation_projects", "label_studio_project_id")


def downgrade() -> None:
    op.add_column(
        "annotation_projects",
        sa.Column("label_studio_project_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "annotation_tasks",
        sa.Column("label_studio_task_id", sa.Integer(), nullable=False, server_default="0"),
    )
