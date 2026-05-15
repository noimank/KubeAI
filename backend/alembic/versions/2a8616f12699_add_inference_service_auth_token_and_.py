"""add inference service auth token and proxy endpoint

Revision ID: 2a8616f12699
Revises: a3ad0231e737
Create Date: 2026-05-15 09:35:19.501852

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2a8616f12699"
down_revision: str | Sequence[str] | None = "a3ad0231e737"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "inference_services",
        sa.Column("auth_token_hash", sa.String(length=255), nullable=True, comment="API Token 哈希"),
    )
    op.add_column(
        "inference_services", sa.Column("proxy_endpoint", sa.String(length=500), nullable=True, comment="代理端点 URL")
    )
    op.create_index(
        op.f("ix_inference_services_auth_token_hash"), "inference_services", ["auth_token_hash"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_inference_services_auth_token_hash"), table_name="inference_services")
    op.drop_column("inference_services", "proxy_endpoint")
    op.drop_column("inference_services", "auth_token_hash")
