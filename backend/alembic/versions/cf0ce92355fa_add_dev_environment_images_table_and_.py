"""add dev_environment_images table and rename dev_environment columns

Revision ID: cf0ce92355fa
Revises: 06ce71516398
Create Date: 2026-05-21 16:23:32.425528

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cf0ce92355fa"
down_revision: str | Sequence[str] | None = "06ce71516398"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0. Add dev_environment_image to resourcetype enum
    op.execute("ALTER TYPE resourcetype ADD VALUE IF NOT EXISTS 'dev_environment_image'")

    # 1. Create dev_environment_images table
    op.create_table(
        "dev_environment_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, comment="环境镜像名称"),
        sa.Column("environment_type", sa.String(length=20), nullable=False, comment="环境类型: jupyter/vscode/rstudio"),
        sa.Column("image_ref", sa.String(length=500), nullable=False, comment="完整容器镜像地址"),
        sa.Column("description", sa.Text(), nullable=True, comment="描述"),
        sa.Column("icon", sa.String(length=100), nullable=True, comment="图标标识"),
        sa.Column("default_cpu", sa.String(length=20), nullable=False, comment="默认 CPU 核数"),
        sa.Column("default_memory", sa.String(length=20), nullable=False, comment="默认内存"),
        sa.Column("default_gpu_count", sa.Integer(), nullable=False, comment="默认 GPU 数量"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, comment="是否启用"),
        sa.Column("tenant_id", sa.Uuid(), nullable=True, comment="租户 ID, null 表示平台级"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", "environment_type", name="uq_dev_env_img_tenant_name_type"),
    )
    op.create_index(op.f("ix_dev_environment_images_tenant_id"), "dev_environment_images", ["tenant_id"], unique=False)

    # 2. Rename columns in dev_environments
    op.alter_column("dev_environments", "jupyterhub_user", new_column_name="spawner_name")
    op.alter_column("dev_environments", "notebook_url", new_column_name="access_url")

    # 3. Drop dead column
    op.drop_column("dev_environments", "pvc_name")

    # 4. Add new columns
    op.add_column(
        "dev_environments", sa.Column("environment_image_id", sa.Uuid(), nullable=True, comment="开发环境镜像 ID")
    )
    op.add_column(
        "dev_environments",
        sa.Column("environment_type", sa.String(length=20), nullable=True, comment="环境类型: jupyter/vscode/rstudio"),
    )
    op.create_foreign_key(
        "fk_dev_environments_environment_image_id",
        "dev_environments",
        "dev_environment_images",
        ["environment_image_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # 4. Remove new columns
    op.drop_constraint("fk_dev_environments_environment_image_id", "dev_environments", type_="foreignkey")
    op.drop_column("dev_environments", "environment_type")
    op.drop_column("dev_environments", "environment_image_id")

    # 3. Restore dead column
    op.add_column(
        "dev_environments",
        sa.Column("pvc_name", sa.VARCHAR(length=100), autoincrement=False, nullable=True, comment="个人 PVC 名称"),
    )

    # 2. Rename columns back
    op.alter_column("dev_environments", "access_url", new_column_name="notebook_url")
    op.alter_column("dev_environments", "spawner_name", new_column_name="jupyterhub_user")

    # 1. Drop dev_environment_images table
    op.drop_index(op.f("ix_dev_environment_images_tenant_id"), table_name="dev_environment_images")
    op.drop_table("dev_environment_images")
