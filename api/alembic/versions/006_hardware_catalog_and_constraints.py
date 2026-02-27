"""Add hardware_models table, provider.category, devices.hardware_model_id, and uniqueness constraints

Revision ID: 006
Revises: 005
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. hardware_models table
    op.create_table(
        "hardware_models",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("manufacturer", sa.String(100), nullable=False, index=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("device_type", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 2. provider.category column
    op.add_column("providers", sa.Column("category", sa.String(50), nullable=True))

    # 3. devices.hardware_model_id FK
    op.add_column(
        "devices",
        sa.Column("hardware_model_id", sa.String(50), sa.ForeignKey("hardware_models.id"), nullable=True),
    )

    # 4. Partial unique indexes for device identifiers
    op.execute("CREATE UNIQUE INDEX uq_devices_imei ON devices(imei) WHERE imei IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_devices_serial_number ON devices(serial_number) WHERE serial_number IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_devices_msisdn ON devices(msisdn) WHERE msisdn IS NOT NULL")

    # 5. Partial unique index for line DID per tenant
    op.execute("CREATE UNIQUE INDEX uq_lines_did_tenant ON lines(did, tenant_id) WHERE did IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_lines_did_tenant")
    op.execute("DROP INDEX IF EXISTS uq_devices_msisdn")
    op.execute("DROP INDEX IF EXISTS uq_devices_serial_number")
    op.execute("DROP INDEX IF EXISTS uq_devices_imei")
    op.drop_column("devices", "hardware_model_id")
    op.drop_column("providers", "category")
    op.drop_table("hardware_models")
