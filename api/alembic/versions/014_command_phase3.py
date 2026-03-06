"""Command Phase 3 — notifications, escalation rules, command telemetry.

Revision ID: 014
Revises: 013
"""

from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Command Notifications --
    op.create_table(
        "command_notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("channel", sa.String(20), nullable=False, server_default="in_app"),  # in_app | email | sms
        sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("incident_id", sa.String(50), nullable=True),
        sa.Column("site_id", sa.String(50), nullable=True),
        sa.Column("target_role", sa.String(50), nullable=True),  # null = all roles
        sa.Column("target_user", sa.String(255), nullable=True),  # null = all users in role
        sa.Column("read", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("read_by", sa.String(255), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cmd_notif_tenant_read", "command_notifications", ["tenant_id", "read"])
    op.create_index("ix_cmd_notif_created", "command_notifications", ["created_at"])

    # -- Escalation Rules --
    op.create_table(
        "escalation_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),  # critical | warning | info
        sa.Column("escalate_after_minutes", sa.Integer, nullable=False, server_default=sa.text("30")),
        sa.Column("escalation_target", sa.String(255), nullable=True),  # email or role
        sa.Column("notify_channel", sa.String(20), nullable=False, server_default="in_app"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- Command Telemetry --
    op.create_table(
        "command_telemetry",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("device_id", sa.String(50), nullable=False, index=True),
        sa.Column("site_id", sa.String(50), nullable=True, index=True),
        sa.Column("signal_strength", sa.Float, nullable=True),     # dBm or 0-100
        sa.Column("battery_pct", sa.Float, nullable=True),         # 0-100
        sa.Column("uptime_seconds", sa.Integer, nullable=True),
        sa.Column("temperature_c", sa.Float, nullable=True),
        sa.Column("error_count", sa.Integer, nullable=True, server_default=sa.text("0")),
        sa.Column("firmware_version", sa.String(50), nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cmd_telem_device_recorded", "command_telemetry", ["device_id", "recorded_at"])

    # -- Add escalation columns to incidents --
    op.add_column("incidents", sa.Column("escalation_level", sa.Integer, nullable=True, server_default=sa.text("0")))
    op.add_column("incidents", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("incidents", "escalated_at")
    op.drop_column("incidents", "escalation_level")
    op.drop_index("ix_cmd_telem_device_recorded", table_name="command_telemetry")
    op.drop_table("command_telemetry")
    op.drop_table("escalation_rules")
    op.drop_index("ix_cmd_notif_created", table_name="command_notifications")
    op.drop_index("ix_cmd_notif_tenant_read", table_name="command_notifications")
    op.drop_table("command_notifications")
