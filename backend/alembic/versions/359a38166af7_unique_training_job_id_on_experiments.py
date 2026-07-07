"""unique training_job_id on experiments

Revision ID: 359a38166af7
Revises: e63bff395ef1
Create Date: 2026-07-07 16:22:31.140494

experiments.training_job_id 收紧为唯一约束: 一个训练任务至多一条 Experiment.
原普通索引替换为唯一约束 (PostgreSQL 自动建唯一索引), 在 DB 层兜底重试/并发
重复插入, 配合 ExperimentService.create_experiment 的幂等 SELECT 保证确定性行为.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "359a38166af7"
down_revision: str | Sequence[str] | None = "e63bff395ef1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 普通索引 → 唯一约束 (唯一约束在 PG 上自带索引, 无需再保留普通索引).
    op.drop_index(op.f("ix_experiments_training_job_id"), table_name="experiments")
    op.create_unique_constraint("uq_experiments_training_job_id", "experiments", ["training_job_id"])


def downgrade() -> None:
    op.drop_constraint("uq_experiments_training_job_id", "experiments", type_="unique")
    op.create_index(op.f("ix_experiments_training_job_id"), "experiments", ["training_job_id"], unique=False)
