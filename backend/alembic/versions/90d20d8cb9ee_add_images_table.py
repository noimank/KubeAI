"""add images table

Revision ID: 90d20d8cb9ee
Revises: 66ce65777a98
Create Date: 2026-05-06 13:45:58.989466

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "90d20d8cb9ee"
down_revision: str | Sequence[str] | None = "66ce65777a98"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, comment="镜像名称"),
        sa.Column("tag", sa.String(length=100), nullable=False, comment="镜像标签/版本"),
        sa.Column("image_ref", sa.String(length=500), nullable=False, comment="完整镜像地址"),
        sa.Column("description", sa.Text(), nullable=True, comment="镜像描述"),
        sa.Column("source", sa.String(length=20), nullable=False, comment="来源"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, comment="是否启用"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("images")
