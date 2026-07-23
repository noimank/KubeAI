"""add db_connections table

Revision ID: 07879f1fcb22
Revises: 13e4ac29cfb9
Create Date: 2026-07-22 11:38:52.210524

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "07879f1fcb22"
down_revision: str | Sequence[str] | None = "13e4ac29cfb9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "db_connections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, comment="连接名称"),
        sa.Column("db_type", sa.String(length=50), nullable=False, comment="数据库类型"),
        sa.Column("host", sa.String(length=500), nullable=False, comment="主机地址"),
        sa.Column("port", sa.Integer(), nullable=False, comment="端口"),
        sa.Column("database_name", sa.String(length=200), nullable=False, comment="数据库名"),
        sa.Column("username", sa.String(length=200), nullable=False, comment="用户名"),
        sa.Column("encrypted_password", sa.Text(), nullable=False, comment="Fernet 加密密码"),
        sa.Column("extra_params", sa.Text(), nullable=True, comment="额外连接参数 JSON"),
        sa.Column("description", sa.String(length=500), nullable=True, comment="备注"),
        sa.Column("created_by", sa.UUID(), nullable=False, comment="创建者"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_db_connections_tenant_name"),
    )
    op.create_index(op.f("ix_db_connections_tenant_id"), "db_connections", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_db_connections_tenant_id"), table_name="db_connections")
    op.drop_table("db_connections")
