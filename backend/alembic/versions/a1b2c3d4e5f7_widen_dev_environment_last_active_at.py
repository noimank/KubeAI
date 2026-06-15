"""widen dev environment last_active_at column

Revision ID: a1b2c3d4e5f7
Revises: f3a4b5c6d7e8
Create Date: 2026-06-15 17:00:00.000000

ISO-format timestamps are 35 characters; the original ``VARCHAR(30)`` truncates
them.  ``VARCHAR(40)`` provides headroom for future timestamp format changes.

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: str | Sequence[str] | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "dev_environments",
        "last_active_at",
        existing_type=sa.String(length=30),
        type_=sa.String(length=40),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "dev_environments",
        "last_active_at",
        existing_type=sa.String(length=35),
        type_=sa.String(length=30),
        existing_nullable=True,
    )
