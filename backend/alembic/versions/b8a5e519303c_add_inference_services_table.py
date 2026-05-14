"""add inference_services table

Revision ID: b8a5e519303c
Revises: 6f912cfa6a91
Create Date: 2026-05-14 16:48:03.985483

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8a5e519303c"
down_revision: str | Sequence[str] | None = "6f912cfa6a91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "inference_services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False, comment="租户 ID"),
        sa.Column("created_by", sa.Uuid(), nullable=False, comment="创建者 ID"),
        sa.Column("name", sa.String(length=100), nullable=False, comment="服务名称"),
        sa.Column("model_version_id", sa.Uuid(), nullable=False, comment="模型版本 ID"),
        sa.Column("image", sa.String(length=500), nullable=True, comment="推理镜像"),
        sa.Column("gpu_count", sa.Integer(), nullable=False, comment="GPU 数量"),
        sa.Column("cpu", sa.String(length=20), nullable=False, comment="CPU 核数"),
        sa.Column("memory", sa.String(length=20), nullable=False, comment="内存"),
        sa.Column("replicas", sa.Integer(), nullable=False, comment="副本数"),
        sa.Column("min_replicas", sa.Integer(), nullable=False, comment="最小副本数"),
        sa.Column("max_replicas", sa.Integer(), nullable=False, comment="最大副本数"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="服务状态"),
        sa.Column("kserve_name", sa.String(length=100), nullable=True, comment="KServe 资源名"),
        sa.Column("endpoint_url", sa.String(length=500), nullable=True, comment="推理端点 URL"),
        sa.Column("description", sa.Text(), nullable=True, comment="描述"),
        sa.Column("env_vars", sa.JSON(), nullable=True, comment="环境变量"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_inference_svc_tenant_name"),
    )
    op.create_index(op.f("ix_inference_services_tenant_id"), "inference_services", ["tenant_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_inference_services_tenant_id"), table_name="inference_services")
    op.drop_table("inference_services")
