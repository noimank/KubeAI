"""add dev_environments table

Revision ID: eef515c83d81
Revises: 7b3c4d5e6f7a
Create Date: 2026-05-20 10:30:57.213577

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "eef515c83d81"
down_revision: str | Sequence[str] | None = "7b3c4d5e6f7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dev_environments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False, comment="租户 ID"),
        sa.Column("created_by", sa.Uuid(), nullable=False, comment="创建者 ID"),
        sa.Column("name", sa.String(length=100), nullable=False, comment="环境名称"),
        sa.Column("image", sa.String(length=500), nullable=False, comment="镜像地址"),
        sa.Column("gpu_count", sa.Integer(), nullable=False, comment="GPU 数量"),
        sa.Column("cpu", sa.String(length=20), nullable=False, comment="CPU 核数"),
        sa.Column("memory", sa.String(length=20), nullable=False, comment="内存"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="环境状态"),
        sa.Column("jupyterhub_user", sa.String(length=100), nullable=True, comment="JupyterHub 用户名"),
        sa.Column("notebook_url", sa.String(length=500), nullable=True, comment="Notebook URL"),
        sa.Column("pvc_name", sa.String(length=100), nullable=True, comment="个人 PVC 名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="描述"),
        sa.Column("env_vars", sa.JSON(), nullable=True, comment="环境变量"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
        sa.Column("last_active_at", sa.String(length=30), nullable=True, comment="上次活跃时间"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_dev_env_tenant_name"),
    )
    op.create_index(op.f("ix_dev_environments_tenant_id"), "dev_environments", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_dev_environments_tenant_id"), table_name="dev_environments")
    op.drop_table("dev_environments")
