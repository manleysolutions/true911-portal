"""Phase 5: org enhancements, site templates, service contracts, outbound webhooks, indexes.

Revision ID: 016
"""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade():
    # --- Extend tenants with org fields ---
    op.add_column("tenants", sa.Column("org_type", sa.String(50), server_default="customer"))
    op.add_column("tenants", sa.Column("parent_tenant_id", sa.String(100), nullable=True))
    op.add_column("tenants", sa.Column("display_name", sa.String(255), nullable=True))
    op.add_column("tenants", sa.Column("logo_url", sa.String(500), nullable=True))
    op.add_column("tenants", sa.Column("primary_color", sa.String(20), nullable=True))
    op.add_column("tenants", sa.Column("contact_email", sa.String(255), nullable=True))
    op.add_column("tenants", sa.Column("contact_phone", sa.String(50), nullable=True))
    op.add_column("tenants", sa.Column("is_active", sa.Boolean(), server_default="true"))
    op.add_column("tenants", sa.Column("settings_json", sa.Text(), nullable=True))

    # --- Site templates ---
    op.create_table(
        "site_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), sa.ForeignKey("tenants.tenant_id"), nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("building_type", sa.String(100), nullable=False),
        sa.Column("systems_json", sa.Text(), nullable=True),
        sa.Column("verification_tasks_json", sa.Text(), nullable=True),
        sa.Column("monitoring_rules_json", sa.Text(), nullable=True),
        sa.Column("readiness_weights_json", sa.Text(), nullable=True),
        sa.Column("is_global", sa.Boolean(), server_default="false"),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- Service contracts ---
    op.create_table(
        "service_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), sa.ForeignKey("tenants.tenant_id"), index=True),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id"), index=True),
        sa.Column("site_id", sa.String(50), nullable=True, index=True),
        sa.Column("contract_type", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_response_minutes", sa.Integer(), nullable=True),
        sa.Column("sla_resolution_hours", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(50), server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- Outbound webhook subscriptions ---
    op.create_table(
        "outbound_webhooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), sa.ForeignKey("tenants.tenant_id"), index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("secret", sa.String(255), nullable=True),
        sa.Column("events", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true"),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("failure_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- Add template_id to sites ---
    op.add_column("sites", sa.Column("template_id", sa.Integer(), nullable=True))
    op.add_column("sites", sa.Column("building_type", sa.String(100), nullable=True))
    op.add_column("sites", sa.Column("onboarding_status", sa.String(50), server_default="active"))

    # --- Performance indexes ---
    op.create_index("ix_incidents_tenant_status", "incidents", ["tenant_id", "status"])
    op.create_index("ix_incidents_tenant_site", "incidents", ["tenant_id", "site_id"])
    op.create_index("ix_incidents_opened_at", "incidents", ["opened_at"])
    op.create_index("ix_command_telemetry_device_recorded", "command_telemetry", ["device_id", "recorded_at"])
    op.create_index("ix_command_telemetry_site_recorded", "command_telemetry", ["site_id", "recorded_at"])
    op.create_index("ix_command_activities_tenant_created", "command_activities", ["tenant_id", "created_at"])
    op.create_index("ix_command_notifications_tenant_read", "command_notifications", ["tenant_id", "read"])
    op.create_index("ix_verification_tasks_tenant_status", "verification_tasks", ["tenant_id", "status"])
    op.create_index("ix_devices_tenant_site", "devices", ["tenant_id", "site_id"])
    op.create_index("ix_devices_tenant_status", "devices", ["tenant_id", "status"])


def downgrade():
    op.drop_index("ix_devices_tenant_status")
    op.drop_index("ix_devices_tenant_site")
    op.drop_index("ix_verification_tasks_tenant_status")
    op.drop_index("ix_command_notifications_tenant_read")
    op.drop_index("ix_command_activities_tenant_created")
    op.drop_index("ix_command_telemetry_site_recorded")
    op.drop_index("ix_command_telemetry_device_recorded")
    op.drop_index("ix_incidents_opened_at")
    op.drop_index("ix_incidents_tenant_site")
    op.drop_index("ix_incidents_tenant_status")
    op.drop_column("sites", "onboarding_status")
    op.drop_column("sites", "building_type")
    op.drop_column("sites", "template_id")
    op.drop_table("outbound_webhooks")
    op.drop_table("service_contracts")
    op.drop_table("site_templates")
    op.drop_column("tenants", "settings_json")
    op.drop_column("tenants", "is_active")
    op.drop_column("tenants", "contact_phone")
    op.drop_column("tenants", "contact_email")
    op.drop_column("tenants", "primary_color")
    op.drop_column("tenants", "logo_url")
    op.drop_column("tenants", "display_name")
    op.drop_column("tenants", "parent_tenant_id")
    op.drop_column("tenants", "org_type")
