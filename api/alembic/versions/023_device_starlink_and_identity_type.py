"""Add starlink_id and identifier_type to devices for Napco/RTL lineup support.

Revision ID: 023
Revises: 022
"""

import sqlalchemy as sa
from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("starlink_id", sa.String(100), nullable=True))
    op.add_column("devices", sa.Column("identifier_type", sa.String(30), nullable=True))
    op.create_index(
        "ix_devices_starlink_id", "devices", ["starlink_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_devices_starlink_id", table_name="devices")
    op.drop_column("devices", "identifier_type")
    op.drop_column("devices", "starlink_id")
