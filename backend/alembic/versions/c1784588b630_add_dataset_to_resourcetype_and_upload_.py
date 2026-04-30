"""add dataset to resourcetype and upload to auditaction enums

Revision ID: c1784588b630
Revises: 66ce65777a98
Create Date: 2026-04-30 13:08:35.809414

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1784588b630"
down_revision: str | Sequence[str] | None = "66ce65777a98"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE resourcetype ADD VALUE IF NOT EXISTS 'dataset'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'upload'")


def downgrade() -> None:
    pass
