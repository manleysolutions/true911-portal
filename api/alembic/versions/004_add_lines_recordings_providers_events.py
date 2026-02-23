"""Add lines, recordings, providers, and events tables

Revision ID: 004
Revises: 003
Create Date: 2026-02-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Lines — logical voice line / DID / SIP connection
    op.create_table(
        "lines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("line_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("site_id", sa.String(50), nullable=True, index=True),
        sa.Column("device_id", sa.String(50), nullable=True, index=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("did", sa.String(30), nullable=True),
        sa.Column("sip_uri", sa.String(255), nullable=True),
        sa.Column("protocol", sa.String(20), nullable=False, server_default="SIP"),
        sa.Column("status", sa.String(30), nullable=False, server_default="provisioning"),
        sa.Column("e911_status", sa.String(20), nullable=False, server_default="none"),
        sa.Column("e911_street", sa.String(500), nullable=True),
        sa.Column("e911_city", sa.String(100), nullable=True),
        sa.Column("e911_state", sa.String(10), nullable=True),
        sa.Column("e911_zip", sa.String(20), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Recordings — provider-agnostic call recording metadata
    op.create_table(
        "recordings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("recording_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("site_id", sa.String(50), nullable=True, index=True),
        sa.Column("device_id", sa.String(50), nullable=True, index=True),
        sa.Column("line_id", sa.String(50), nullable=True, index=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("call_control_id", sa.String(100), nullable=True),
        sa.Column("cdr_id", sa.String(100), nullable=True),
        sa.Column("recording_url", sa.String(1000), nullable=True),
        sa.Column("direction", sa.String(10), nullable=False, server_default="inbound"),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("caller", sa.String(50), nullable=True),
        sa.Column("callee", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="available"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Providers — integration config references
    op.create_table(
        "providers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("provider_type", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("api_key_ref", sa.String(255), nullable=True),
        sa.Column("enabled", sa.Boolean, server_default=sa.text("false")),
        sa.Column("config_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Events — unified immutable event log
    op.create_table(
        "events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("event_type", sa.String(50), nullable=False, index=True),
        sa.Column("site_id", sa.String(50), nullable=True, index=True),
        sa.Column("device_id", sa.String(50), nullable=True),
        sa.Column("line_id", sa.String(50), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("providers")
    op.drop_table("recordings")
    op.drop_table("lines")
