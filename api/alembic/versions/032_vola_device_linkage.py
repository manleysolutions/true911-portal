"""Add VOLA linkage fields to devices.

Revision ID: 032
Revises: 031
"""

from alembic import op
import sqlalchemy as sa

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("vola_org_id", sa.String(100), nullable=True))
    op.add_column("devices", sa.Column("vola_last_sync", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("vola_last_task_id", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "vola_last_task_id")
    op.drop_column("devices", "vola_last_sync")
    op.drop_column("devices", "vola_org_id")
