"""add_oauth_fields_to_users

Revision ID: a1b2c3d4e5f6
Revises: 9e97da58e58e
Create Date: 2026-04-29 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "9e97da58e58e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_provider", sa.String(20), server_default="local", nullable=False))
    op.add_column("users", sa.Column("external_id", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_users_auth_provider_external_id", "users", ["auth_provider", "external_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_auth_provider_external_id", "users", type_="unique")
    op.drop_column("users", "external_id")
    op.drop_column("users", "auth_provider")
