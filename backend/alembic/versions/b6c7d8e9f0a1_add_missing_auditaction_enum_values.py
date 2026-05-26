"""add missing auditaction enum values

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-05-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b6c7d8e9f0a1"
down_revision: str | None = "a5b6c7d8e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sa.Enum("cleanup_job", "transfer_quota", name="auditaction").create(op.get_bind(), checkfirst=True)

    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'cleanup_job'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'transfer_quota'")


def downgrade() -> None:
    op.execute("DELETE FROM audit_logs WHERE action IN ('cleanup_job', 'transfer_quota')")
    op.execute("ALTER TYPE auditaction RENAME TO auditaction_old")
    op.execute(
        "CREATE TYPE auditaction AS ENUM ("
        "'create', 'update', 'delete', 'login', 'logout', 'register', "
        "'enable', 'disable', 'invite', 'accept_invite', 'cancel_invite', "
        "'update_role', 'add_member', 'remove_member', 'update_quota', "
        "'upload', 'build', 'rebuild'"
        ")"
    )
    op.execute("ALTER TABLE audit_logs ALTER COLUMN action TYPE auditaction USING action::text::auditaction")
    op.execute("DROP TYPE auditaction_old")
