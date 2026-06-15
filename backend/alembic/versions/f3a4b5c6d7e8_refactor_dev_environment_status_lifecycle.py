"""refactor dev environment status lifecycle

Revision ID: f3a4b5c6d7e8
Revises: a9f1c4d2e6b8
Create Date: 2026-06-15 10:00:00.000000

Breaking changes to the dev environment status machine:
- Rename ``creating`` → ``starting`` (covers first-time create AND restart)
- Add ``stopping`` transitional status
- Drop the legacy ``spawner_name`` column (JupyterHub-era remnant; the native
  pod manager derives resource names from the env UUID hex, so this column was
  never consumed by the K8s layer)

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: str | Sequence[str] | None = "a9f1c4d2e6b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Migrate existing rows: creating → starting.
    # (starting/stopping are new values; the status column is a free-form string
    # so no enum alteration is needed.)
    op.execute("UPDATE dev_environments SET status = 'starting' WHERE status = 'creating'")

    # Drop the JupyterHub-era spawner_name column — the native pod manager uses
    # ``devenv-<env_uuid_hex>`` as the K8s resource name and never reads this.
    op.drop_column("dev_environments", "spawner_name")


def downgrade() -> None:
    op.add_column(
        "dev_environments",
        sa.Column("spawner_name", sa.String(length=100), nullable=True, comment="Spawner 名称"),
    )
    op.execute("UPDATE dev_environments SET status = 'creating' WHERE status = 'starting'")
