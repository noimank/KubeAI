"""add business_configs table and training env_vars

Revision ID: 60ae4c43d889
Revises: 07879f1fcb22
Create Date: 2026-07-29 10:28:09.584265

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "60ae4c43d889"
down_revision: str | Sequence[str] | None = "07879f1fcb22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False, comment="租户 ID"),
        sa.Column("created_by", sa.Uuid(), nullable=False, comment="创建者 ID"),
        sa.Column("name", sa.String(length=100), nullable=False, comment="配置名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="描述"),
        sa.Column("env_vars", sa.JSON(), nullable=False, comment="环境变量键值对"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_biz_cfg_tenant_name"),
    )
    op.create_index(op.f("ix_business_configs_tenant_id"), "business_configs", ["tenant_id"], unique=False)
    op.add_column(
        "training_jobs",
        sa.Column("env_vars", sa.JSON(), nullable=True, comment="环境变量"),
    )


def downgrade() -> None:
    op.drop_column("training_jobs", "env_vars")
    op.drop_index(op.f("ix_business_configs_tenant_id"), table_name="business_configs")
    op.drop_table("business_configs")
