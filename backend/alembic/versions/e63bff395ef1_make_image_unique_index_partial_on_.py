"""make image unique index partial on deleted_at

Revision ID: e63bff395ef1
Revises: e7c4a92f1b68
Create Date: 2026-07-03 10:37:14.683605

将 images 表的 (tenant_id, category, name, tag) 唯一约束改为部分唯一索引
(WHERE deleted_at IS NULL): 软删除的记录不再占用唯一约束, 删除后可用相同
name/tag 重新添加镜像, 避免残留软删记录导致重名镜像插入失败.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e63bff395ef1"
down_revision: str | Sequence[str] | None = "e7c4a92f1b68"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 唯一约束 → 部分唯一索引: 仅约束未软删行, 软删后同名镜像可重新添加
    op.drop_constraint("uq_image_tenant_category_name_tag", "images", type_="unique")
    op.create_index(
        "uq_image_tenant_category_name_tag",
        "images",
        ["tenant_id", "category", "name", "tag"],
        unique=True,
        postgresql_where="deleted_at IS NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_image_tenant_category_name_tag", table_name="images", postgresql_where="deleted_at IS NULL")
    op.create_unique_constraint("uq_image_tenant_category_name_tag", "images", ["tenant_id", "category", "name", "tag"])
