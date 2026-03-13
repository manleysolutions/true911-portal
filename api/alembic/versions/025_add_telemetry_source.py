"""Add telemetry_source column to devices.

Tracks the last source that provided telemetry for this device
(e.g. "pr12_heartbeat", "inseego_heartbeat", "verizon_carrier",
"vola_api").  Nullable — old devices simply have NULL until their
first telemetry update.

Revision ID: 025
Revises: 024
"""

import sqlalchemy as sa
from alembic import op

revision = "025"
down_revision = "024"


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("telemetry_source", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("devices", "telemetry_source")
