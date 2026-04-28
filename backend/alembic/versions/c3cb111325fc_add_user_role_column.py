"""add_user_role_column

Revision ID: c3cb111325fc
Revises: 4c7e5cab967a
Create Date: 2026-04-28 12:17:23.154275

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3cb111325fc"
down_revision: str | Sequence[str] | None = "4c7e5cab967a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


userrole = sa.Enum("admin", "mlops", "engineer", "annotator", name="userrole")


def upgrade() -> None:
    """Upgrade schema."""
    userrole.create(op.get_bind(), checkfirst=True)
    op.add_column("users", sa.Column("role", userrole, server_default="engineer", nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "role")
    userrole.drop(op.get_bind(), checkfirst=True)
