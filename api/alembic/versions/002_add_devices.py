"""Add devices table

Revision ID: 002
Revises: 001
Create Date: 2026-02-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("device_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("site_id", sa.String(50), nullable=True, index=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("device_type", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("serial_number", sa.String(100), nullable=True, index=True),
        sa.Column("mac_address", sa.String(50), nullable=True),
        sa.Column("imei", sa.String(50), nullable=True),
        sa.Column("firmware_version", sa.String(50), nullable=True),
        sa.Column("container_version", sa.String(50), nullable=True),
        sa.Column("provision_code", sa.String(100), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_interval", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("devices")
