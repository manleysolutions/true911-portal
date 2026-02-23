"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tenants
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("tenant_id", sa.String(100), sa.ForeignKey("tenants.tenant_id"), nullable=False, index=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Sites
    op.create_table(
        "sites",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("site_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), sa.ForeignKey("tenants.tenant_id"), nullable=False, index=True),
        sa.Column("site_name", sa.String(255), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("last_checkin", sa.DateTime, nullable=True),
        sa.Column("e911_street", sa.String(500), nullable=True),
        sa.Column("e911_city", sa.String(100), nullable=True),
        sa.Column("e911_state", sa.String(10), nullable=True),
        sa.Column("e911_zip", sa.String(20), nullable=True),
        sa.Column("poc_name", sa.String(255), nullable=True),
        sa.Column("poc_phone", sa.String(50), nullable=True),
        sa.Column("poc_email", sa.String(255), nullable=True),
        sa.Column("device_model", sa.String(100), nullable=True),
        sa.Column("device_serial", sa.String(100), nullable=True),
        sa.Column("device_firmware", sa.String(50), nullable=True),
        sa.Column("kit_type", sa.String(100), nullable=True),
        sa.Column("carrier", sa.String(100), nullable=True),
        sa.Column("static_ip", sa.String(50), nullable=True),
        sa.Column("signal_dbm", sa.Integer, nullable=True),
        sa.Column("network_tech", sa.String(50), nullable=True),
        sa.Column("heartbeat_frequency", sa.String(50), nullable=True),
        sa.Column("heartbeat_next_due", sa.DateTime, nullable=True),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lng", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("endpoint_type", sa.String(100), nullable=True),
        sa.Column("service_class", sa.String(100), nullable=True),
        sa.Column("last_device_heartbeat", sa.DateTime, nullable=True),
        sa.Column("last_portal_sync", sa.DateTime, nullable=True),
        sa.Column("container_version", sa.String(50), nullable=True),
        sa.Column("firmware_version", sa.String(50), nullable=True),
        sa.Column("csa_model", sa.String(100), nullable=True),
        sa.Column("heartbeat_interval", sa.Integer, nullable=True),
        sa.Column("uptime_percent", sa.Float, nullable=True),
        sa.Column("update_channel", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Telemetry Events
    op.create_table(
        "telemetry_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("site_id", sa.String(50), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("timestamp", sa.DateTime, nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("raw_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Action Audits
    op.create_table(
        "action_audits",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("audit_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("request_id", sa.String(50), nullable=True, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("requester_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("action_type", sa.String(50), nullable=True),
        sa.Column("site_id", sa.String(50), nullable=True, index=True),
        sa.Column("timestamp", sa.DateTime, nullable=True),
        sa.Column("result", sa.String(20), nullable=True),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Incidents
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("incident_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("site_id", sa.String(50), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("opened_at", sa.DateTime, nullable=True),
        sa.Column("ack_by", sa.String(255), nullable=True),
        sa.Column("ack_at", sa.DateTime, nullable=True),
        sa.Column("closed_at", sa.DateTime, nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("assigned_to", sa.String(255), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Notification Rules
    op.create_table(
        "notification_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("rule_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("rule_name", sa.String(255), nullable=False),
        sa.Column("rule_type", sa.String(100), nullable=False),
        sa.Column("threshold_value", sa.Float, nullable=False),
        sa.Column("threshold_unit", sa.String(50), nullable=False),
        sa.Column("scope", sa.String(100), nullable=False),
        sa.Column("channels", postgresql.JSONB, server_default="[]"),
        sa.Column("enabled", sa.Boolean, server_default=sa.text("true")),
        sa.Column("escalation_steps", postgresql.JSONB, server_default="[]"),
        sa.Column("trigger_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("last_triggered", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # E911 Change Logs
    op.create_table(
        "e911_change_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("log_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("site_id", sa.String(50), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("requester_name", sa.String(255), nullable=True),
        sa.Column("requested_at", sa.DateTime, nullable=True),
        sa.Column("old_street", sa.String(500), nullable=True),
        sa.Column("old_city", sa.String(100), nullable=True),
        sa.Column("old_state", sa.String(10), nullable=True),
        sa.Column("old_zip", sa.String(20), nullable=True),
        sa.Column("new_street", sa.String(500), nullable=True),
        sa.Column("new_city", sa.String(100), nullable=True),
        sa.Column("new_state", sa.String(10), nullable=True),
        sa.Column("new_zip", sa.String(20), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("applied_at", sa.DateTime, nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("e911_change_logs")
    op.drop_table("notification_rules")
    op.drop_table("incidents")
    op.drop_table("action_audits")
    op.drop_table("telemetry_events")
    op.drop_table("sites")
    op.drop_table("users")
    op.drop_table("tenants")
