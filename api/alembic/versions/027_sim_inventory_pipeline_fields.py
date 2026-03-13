"""Add inventory pipeline fields to sims table.

New columns for carrier-sync ingestion:
  - imei, device_id (pairing)
  - network_status, activation_status (carrier state)
  - last_synced_at (sync timestamp)
  - data_source (manual vs carrier-synced)
  - inferred_lat, inferred_lng, inferred_location_source (carrier geodata)

Revision ID: 027
Revises: 026
"""

from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sims", sa.Column("imei", sa.String(50), nullable=True))
    op.add_column("sims", sa.Column("device_id", sa.String(50), nullable=True, index=True))
    op.add_column("sims", sa.Column("network_status", sa.String(50), nullable=True))
    op.add_column("sims", sa.Column("activation_status", sa.String(50), nullable=True))
    op.add_column("sims", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sims", sa.Column("data_source", sa.String(30), nullable=True, server_default="manual"))
    op.add_column("sims", sa.Column("inferred_lat", sa.Float, nullable=True))
    op.add_column("sims", sa.Column("inferred_lng", sa.Float, nullable=True))
    op.add_column("sims", sa.Column("inferred_location_source", sa.String(50), nullable=True))


def downgrade() -> None:
    for col in ("inferred_location_source", "inferred_lng", "inferred_lat",
                "data_source", "last_synced_at", "activation_status",
                "network_status", "device_id", "imei"):
        op.drop_column("sims", col)
