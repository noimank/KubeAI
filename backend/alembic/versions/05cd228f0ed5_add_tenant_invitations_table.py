"""add tenant invitations table

Revision ID: 05cd228f0ed5
Revises: b2c3d4e5f6a7
Create Date: 2026-04-29 14:29:36.802838

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "05cd228f0ed5"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

invitationstatus = postgresql.ENUM(
    "pending",
    "accepted",
    "cancelled",
    "expired",
    name="invitationstatus",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    invitationstatus.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "tenant_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), server_default="engineer", nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("status", invitationstatus, server_default="pending", nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=False),
        sa.Column("accepted_by", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["accepted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenant_invitations_email"), "tenant_invitations", ["email"], unique=False)
    op.create_index(op.f("ix_tenant_invitations_tenant_id"), "tenant_invitations", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_tenant_invitations_token"), "tenant_invitations", ["token"], unique=True)
    op.create_index(
        "uq_invitations_tenant_email_pending",
        "tenant_invitations",
        ["tenant_id", "email"],
        unique=True,
        postgresql_where="status = 'pending'",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_invitations_tenant_email_pending", table_name="tenant_invitations", postgresql_where="status = 'pending'"
    )
    op.drop_index(op.f("ix_tenant_invitations_token"), table_name="tenant_invitations")
    op.drop_index(op.f("ix_tenant_invitations_tenant_id"), table_name="tenant_invitations")
    op.drop_index(op.f("ix_tenant_invitations_email"), table_name="tenant_invitations")
    op.drop_table("tenant_invitations")
    invitationstatus.drop(op.get_bind(), checkfirst=True)
