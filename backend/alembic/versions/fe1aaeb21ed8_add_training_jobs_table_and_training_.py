"""add training_jobs table and training_job enum

Revision ID: fe1aaeb21ed8
Revises: c7bbf20fc037
Create Date: 2026-05-07 16:56:27.975280

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fe1aaeb21ed8"
down_revision: str | Sequence[str] | None = "c7bbf20fc037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE resourcetype ADD VALUE IF NOT EXISTS 'training_job'")
    op.create_table(
        "training_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False, comment="租户 ID"),
        sa.Column("name", sa.String(length=100), nullable=False, comment="任务名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="任务描述"),
        sa.Column("created_by", sa.Uuid(), nullable=False, comment="创建者 ID"),
        sa.Column("dataset_id", sa.Uuid(), nullable=True, comment="数据集 ID"),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=True, comment="数据集版本 ID"),
        sa.Column("image_id", sa.Uuid(), nullable=False, comment="镜像 ID"),
        sa.Column("command", sa.Text(), nullable=False, comment="启动命令"),
        sa.Column("hyperparameters", sa.JSON(), nullable=True, comment="超参数"),
        sa.Column("gpu_count", sa.Integer(), nullable=False, comment="GPU 数量"),
        sa.Column("gpu_mode", sa.String(length=20), nullable=False, comment="GPU 模式"),
        sa.Column("cpu", sa.String(length=20), nullable=False, comment="CPU 核数"),
        sa.Column("memory", sa.String(length=20), nullable=False, comment="内存"),
        sa.Column("priority", sa.String(length=20), nullable=False, comment="优先级"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="任务状态"),
        sa.Column("vcjob_name", sa.String(length=100), nullable=True, comment="Volcano Job 名称"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True, comment="开始时间"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True, comment="结束时间"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_training_job_tenant_name"),
    )
    op.create_index(op.f("ix_training_jobs_tenant_id"), "training_jobs", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_training_jobs_tenant_id"), table_name="training_jobs")
    op.drop_table("training_jobs")
