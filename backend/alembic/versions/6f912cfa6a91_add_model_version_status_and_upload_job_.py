"""add model version status and upload job name

Revision ID: 6f912cfa6a91
Revises: e6d8da0bdf31
Create Date: 2026-05-14 11:41:52.453430

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f912cfa6a91"
down_revision: str | Sequence[str] | None = "e6d8da0bdf31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_versions", sa.Column("status", sa.String(length=20), nullable=False, server_default="uploading")
    )
    op.add_column("model_versions", sa.Column("upload_job_name", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("model_versions", "upload_job_name")
    op.drop_column("model_versions", "status")
