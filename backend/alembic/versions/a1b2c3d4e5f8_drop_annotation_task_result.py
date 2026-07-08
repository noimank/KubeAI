"""drop annotation_task_result

AnnotationTask.result 是 DB 层的"标注结果"副本, 与文件系统 annotations/<name>.json
重复存储, 无约束保持一致. 改为以文件系统为唯一真理, 删除此列.

Revision ID: a1b2c3d4e5f8
Revises: 4e1b0cdc1380
Create Date: 2026-07-08 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f8"
down_revision: str | Sequence[str] | None = "4e1b0cdc1380"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("annotation_tasks", "result")


def downgrade() -> None:
    op.add_column(
        "annotation_tasks",
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
