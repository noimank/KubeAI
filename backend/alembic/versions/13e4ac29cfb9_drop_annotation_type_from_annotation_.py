"""drop annotation_type from annotation_projects

Revision ID: 13e4ac29cfb9
Revises: a1b2c3d4e5f9
Create Date: 2026-07-13 17:40:34.346271

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "13e4ac29cfb9"
down_revision: str | None = "a1b2c3d4e5f9"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_column("annotation_projects", "annotation_type")


def downgrade() -> None:
    op.add_column(
        "annotation_projects",
        sa.Column("annotation_type", sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    )
