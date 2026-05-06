"""add image to resourcetype enum

Revision ID: 6fcbd81cac10
Revises: 90d20d8cb9ee
Create Date: 2026-05-06 14:18:17.608889

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6fcbd81cac10"
down_revision: str | Sequence[str] | None = "90d20d8cb9ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE resourcetype ADD VALUE IF NOT EXISTS 'image'")


def downgrade() -> None:
    pass
