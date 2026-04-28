"""add_tenants_table_and_user_tenant_id

Revision ID: 9e97da58e58e
Revises: c3cb111325fc
Create Date: 2026-04-28 14:35:51.849474

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e97da58e58e"
down_revision: str | Sequence[str] | None = "c3cb111325fc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


tenantstatus = sa.Enum("active", "disabled", name="tenantstatus")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", tenantstatus, server_default="active", nullable=False),
        sa.Column("k8s_namespace_name", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.add_column("users", sa.Column("tenant_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_users_tenant_id"), "users", ["tenant_id"], unique=False)
    op.create_foreign_key("fk_users_tenant_id", "users", "tenants", ["tenant_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_users_tenant_id", "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_tenant_id"), table_name="users")
    op.drop_column("users", "tenant_id")
    op.drop_table("tenants")
    tenantstatus.drop(op.get_bind(), checkfirst=True)
