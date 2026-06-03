"""add algorithm to resourcetype and download to auditaction enums

Revision ID: a9f1c4d2e6b8
Revises: 78f2cc35add3
Create Date: 2026-06-03 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9f1c4d2e6b8"
down_revision: str | Sequence[str] | None = "78f2cc35add3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sa.Enum("download", name="auditaction").create(op.get_bind(), checkfirst=True)
    sa.Enum("algorithm", name="resourcetype").create(op.get_bind(), checkfirst=True)

    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'download'")
    op.execute("ALTER TYPE resourcetype ADD VALUE IF NOT EXISTS 'algorithm'")


def downgrade() -> None:
    op.execute("DELETE FROM audit_logs WHERE resource_type = 'algorithm'")
    op.execute("DELETE FROM audit_logs WHERE action = 'download'")

    op.execute("ALTER TYPE resourcetype RENAME TO resourcetype_old")
    op.execute(
        "CREATE TYPE resourcetype AS ENUM ("
        "'tenant', 'user', 'quota', 'membership', 'invitation', "
        "'credential', 'dataset', 'image', 'dev_environment_image', "
        "'training_job', 'model', 'annotation_project'"
        ")"
    )
    op.execute(
        "ALTER TABLE audit_logs ALTER COLUMN resource_type TYPE resourcetype USING resource_type::text::resourcetype"
    )
    op.execute("DROP TYPE resourcetype_old")

    op.execute("ALTER TYPE auditaction RENAME TO auditaction_old")
    op.execute(
        "CREATE TYPE auditaction AS ENUM ("
        "'create', 'update', 'delete', 'login', 'logout', 'register', "
        "'enable', 'disable', 'invite', 'accept_invite', 'cancel_invite', "
        "'update_role', 'add_member', 'remove_member', 'update_quota', "
        "'upload', 'build', 'rebuild', 'cleanup_job', 'transfer_quota'"
        ")"
    )
    op.execute("ALTER TABLE audit_logs ALTER COLUMN action TYPE auditaction USING action::text::auditaction")
    op.execute("DROP TYPE auditaction_old")
