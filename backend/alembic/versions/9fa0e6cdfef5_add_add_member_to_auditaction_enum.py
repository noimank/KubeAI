"""add add_member to auditaction enum

Revision ID: 9fa0e6cdfef5
Revises: c1784588b630
Create Date: 2026-05-01 17:02:37.800478

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9fa0e6cdfef5"
down_revision: str | Sequence[str] | None = "c1784588b630"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'add_member'")


def downgrade() -> None:
    pass
