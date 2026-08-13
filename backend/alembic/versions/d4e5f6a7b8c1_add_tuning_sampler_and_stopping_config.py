"""add tuning sampler_config / stopping_config

- tuning_studies.sampler_config: 采样器配置 (搜索策略 TPE/CMA-ES/Random + seed),
  RDBStorage 不持久化 sampler, 创建与每次调度 tick 由 build_sampler 从该配置重建.
- tuning_studies.stopping_config: 终止条件配置 (study 超时 / trial 超时 / 早停耐心).

两列均可空, 为空走默认 TPE / 无额外终止条件.

Revision ID: d4e5f6a7b8c1
Revises: c4d5e6f7a8b9
Create Date: 2026-08-11 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c1"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tuning_studies",
        sa.Column("sampler_config", sa.JSON(), nullable=True, comment="采样器配置"),
    )
    op.add_column(
        "tuning_studies",
        sa.Column("stopping_config", sa.JSON(), nullable=True, comment="终止条件配置"),
    )


def downgrade() -> None:
    op.drop_column("tuning_studies", "stopping_config")
    op.drop_column("tuning_studies", "sampler_config")
