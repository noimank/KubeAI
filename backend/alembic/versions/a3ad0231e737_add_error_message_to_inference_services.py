"""add error_message to inference_services

Revision ID: a3ad0231e737
Revises: b8a5e519303c
Create Date: 2026-05-14 17:01:46.738113

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3ad0231e737"
down_revision: str | Sequence[str] | None = "b8a5e519303c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("inference_services", sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("inference_services", "error_message")
