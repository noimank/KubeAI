"""add tuning_studies and tuning_trials tables

Revision ID: 9f8e7d6c5b4a
Revises: 60ae4c43d889
Create Date: 2026-08-03 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f8e7d6c5b4a"
down_revision: str | Sequence[str] | None = "60ae4c43d889"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tuning_studies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False, comment="租户 ID"),
        sa.Column("created_by", sa.Uuid(), nullable=False, comment="创建者 ID"),
        sa.Column("name", sa.String(length=100), nullable=False, comment="调优任务名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="描述"),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="running",
            nullable=False,
            comment="调优状态: running/completed/stopped/failed",
        ),
        sa.Column(
            "direction",
            sa.String(length=10),
            server_default="minimize",
            nullable=False,
            comment="优化方向: minimize/maximize",
        ),
        sa.Column("metric_name", sa.String(length=100), nullable=False, comment="目标指标名称 (MLflow metric key)"),
        sa.Column("n_trials", sa.Integer(), nullable=False, server_default="10", comment="试验总数"),
        sa.Column("n_jobs", sa.Integer(), nullable=False, server_default="1", comment="并发试验上限"),
        sa.Column("search_space", sa.JSON(), nullable=False, comment="搜索空间定义"),
        sa.Column("image_id", sa.Uuid(), nullable=False, comment="镜像 ID"),
        sa.Column("dataset_id", sa.Uuid(), nullable=True, comment="数据集 ID"),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=True, comment="数据集版本 ID"),
        sa.Column("command", sa.Text(), nullable=False, comment="训练命令"),
        sa.Column("gpu_count", sa.Integer(), nullable=False, server_default="1", comment="GPU 数量"),
        sa.Column(
            "gpu_mode",
            sa.String(length=20),
            server_default="exclusive",
            nullable=False,
            comment="GPU 模式",
        ),
        sa.Column("cpu", sa.String(length=20), server_default="4", nullable=False, comment="CPU 核数"),
        sa.Column("memory", sa.String(length=20), server_default="8Gi", nullable=False, comment="内存"),
        sa.Column(
            "priority",
            sa.String(length=20),
            server_default="normal",
            nullable=False,
            comment="优先级",
        ),
        sa.Column("worker_count", sa.Integer(), nullable=False, server_default="1", comment="Worker 数量"),
        sa.Column("env_vars", sa.JSON(), nullable=True, comment="附加到每个 trial 的环境变量"),
        sa.Column(
            "optuna_study_name",
            sa.String(length=100),
            nullable=False,
            comment="Optuna study 名称 (唯一, 对应 RDBStorage 中的 study)",
        ),
        sa.Column("best_value", sa.Float(), nullable=True, comment="最佳指标值"),
        sa.Column("best_trial_number", sa.Integer(), nullable=True, comment="最佳 trial 序号"),
        sa.Column("best_params", sa.JSON(), nullable=True, comment="最佳超参"),
        sa.Column(
            "best_training_job_id",
            sa.Uuid(),
            nullable=True,
            comment="最佳 trial 的训练任务 ID",
        ),
        sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["best_training_job_id"], ["training_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_tuning_studies_tenant_name"),
        sa.UniqueConstraint("optuna_study_name", name="uq_tuning_studies_optuna_study_name"),
    )
    op.create_index(op.f("ix_tuning_studies_tenant_id"), "tuning_studies", ["tenant_id"], unique=False)

    op.create_table(
        "tuning_trials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False, comment="调优任务 ID"),
        sa.Column("trial_number", sa.Integer(), nullable=False, comment="Optuna trial 序号"),
        sa.Column(
            "training_job_id",
            sa.Uuid(),
            nullable=True,
            comment="训练任务 ID (trial job 被单独删除时置空, 该 trial 由调度器记为 FAIL)",
        ),
        sa.Column("params", sa.JSON(), nullable=True, comment="采样超参快照"),
        sa.Column(
            "state",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
            comment="trial 状态: pending/running/complete/failed/pruned",
        ),
        sa.Column(
            "told",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="是否已上报 Optuna (幂等标志)",
        ),
        sa.Column("value", sa.Float(), nullable=True, comment="已上报的指标值"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["study_id"], ["tuning_studies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["training_job_id"], ["training_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_id", "trial_number", name="uq_tuning_trials_study_number"),
        sa.UniqueConstraint("training_job_id", name="uq_tuning_trials_training_job"),
    )
    op.create_index(op.f("ix_tuning_trials_study_id"), "tuning_trials", ["study_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tuning_trials_study_id"), table_name="tuning_trials")
    op.drop_table("tuning_trials")
    op.drop_index(op.f("ix_tuning_studies_tenant_id"), table_name="tuning_studies")
    op.drop_table("tuning_studies")
