"""add annotation templates table and template_id fk on annotation_projects

Revision ID: a1b2c3d4e5f9
Revises: a1b2c3d4e5f8
Create Date: 2026-07-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f9"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 扩展 audit_log.resource_type 枚举
    op.execute("ALTER TYPE resourcetype ADD VALUE IF NOT EXISTS 'annotation_template'")

    op.create_table(
        "annotation_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False, comment="租户 ID"),
        sa.Column("user_id", sa.Uuid(), nullable=False, comment="创建者 ID"),
        sa.Column("name", sa.String(length=200), nullable=False, comment="模板名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="模板描述"),
        sa.Column("label_config", sa.Text(), nullable=False, comment="Label Studio XML 配置"),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="标签列表",
        ),
        sa.Column("group", sa.String(length=100), nullable=False, server_default=sa.text("'其他'"), comment="所属分组"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_annotation_templates_tenant_name"),
    )
    op.create_index(op.f("ix_annotation_templates_tenant_id"), "annotation_templates", ["tenant_id"], unique=False)
    op.create_index(
        "ix_annotation_templates_tags",
        "annotation_templates",
        ["tags"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"tags": "jsonb_path_ops"},
    )
    op.create_index("ix_annotation_templates_group", "annotation_templates", ["group"], unique=False)

    # 标注项目加模板外键 + label_config 改可空 (保留为创建时快照, worker 路径不变)
    op.add_column(
        "annotation_projects",
        sa.Column("template_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_annotation_projects_template_id",
        "annotation_projects",
        "annotation_templates",
        ["template_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("annotation_projects", "label_config", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("annotation_projects", "label_config", existing_type=sa.Text(), nullable=False)
    op.drop_constraint("fk_annotation_projects_template_id", "annotation_projects", type_="foreignkey")
    op.drop_column("annotation_projects", "template_id")
    op.drop_index("ix_annotation_templates_group", table_name="annotation_templates")
    op.drop_index("ix_annotation_templates_tags", table_name="annotation_templates")
    op.drop_index(op.f("ix_annotation_templates_tenant_id"), table_name="annotation_templates")
    op.drop_table("annotation_templates")
    # 注意: ALTER TYPE ... ADD VALUE 在 PG 中不能事务回滚, 枚举值不会随 downgrade 移除
