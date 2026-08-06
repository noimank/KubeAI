"""refactor tuning: drop told/best cache, add pruning config

- 删除 tuning_trials.told (幂等判定改为基于 Optuna trial state)
- 删除 tuning_studies 的 best_trial_number/best_params/best_training_job_id
  (best 单一来源: 列表页用 reconcile 折算的 best_value, 详情页实时查 Optuna)
- 新增 tuning_studies.pruning_enabled/pruning_config (阈值剪枝, 默认关闭)

Revision ID: c4d5e6f7a8b9
Revises: 9f8e7d6c5b4a
Create Date: 2026-08-05 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = "9f8e7d6c5b4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ① best 缓存列: 仅保留 best_value (reconcile 折算), 删除其余 3 列.
    op.drop_constraint("tuning_studies_best_training_job_id_fkey", "tuning_studies", type_="foreignkey")
    op.drop_column("tuning_studies", "best_training_job_id")
    op.drop_column("tuning_studies", "best_params")
    op.drop_column("tuning_studies", "best_trial_number")

    # ② pruning 配置 (默认关闭).
    op.add_column(
        "tuning_studies",
        sa.Column(
            "pruning_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False, comment="是否启用剪枝"
        ),
    )
    op.add_column(
        "tuning_studies",
        sa.Column("pruning_config", sa.JSON(), nullable=True, comment="剪枝配置"),
    )

    # ③ told 字段: 幂等改由 Optuna trial state 判定, 平台不再维护此标志.
    op.drop_column("tuning_trials", "told")


def downgrade() -> None:
    op.add_column(
        "tuning_trials",
        sa.Column(
            "told",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="是否已上报 Optuna (幂等标志)",
        ),
    )

    op.drop_column("tuning_studies", "pruning_config")
    op.drop_column("tuning_studies", "pruning_enabled")

    op.add_column(
        "tuning_studies", sa.Column("best_trial_number", sa.Integer(), nullable=True, comment="最佳 trial 序号")
    )
    op.add_column("tuning_studies", sa.Column("best_params", sa.JSON(), nullable=True, comment="最佳超参"))
    op.add_column(
        "tuning_studies",
        sa.Column("best_training_job_id", sa.Uuid(), nullable=True, comment="最佳 trial 的训练任务 ID"),
    )
    op.create_foreign_key(
        "tuning_studies_best_training_job_id_fkey",
        "tuning_studies",
        "training_jobs",
        ["best_training_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
