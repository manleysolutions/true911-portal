"""017 – Network & Public Safety Integration Layer (Phase 7)

New tables:
  - network_events          carrier/network event log
  - infra_tests             automated test definitions
  - infra_test_results      test execution outcomes
  - audit_log_entries       unified infrastructure audit trail

Column additions:
  - devices: carrier, sim_id, imsi, network_status, data_usage_mb, last_network_event
  - sites: psap_id, emergency_class, ng911_uri
  - incidents: category

Performance indexes on new + existing tables.
"""

from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── network_events ──────────────────────────────────────────────
    op.create_table(
        "network_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("device_id", sa.String(50), nullable=False, index=True),
        sa.Column("site_id", sa.String(50), nullable=True, index=True),
        sa.Column("carrier", sa.String(50), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("detail_json", sa.Text, nullable=True),
        sa.Column("signal_dbm", sa.Float, nullable=True),
        sa.Column("network_status", sa.String(50), nullable=True),
        sa.Column("roaming", sa.Boolean, nullable=True, server_default="false"),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("incident_id", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── infra_tests ─────────────────────────────────────────────────
    op.create_table(
        "infra_tests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("test_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("test_type", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("site_id", sa.String(50), nullable=True),
        sa.Column("device_id", sa.String(50), nullable=True),
        sa.Column("schedule_cron", sa.String(100), nullable=True),
        sa.Column("run_after_provision", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("config_json", sa.Text, nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_result", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── infra_test_results ──────────────────────────────────────────
    op.create_table(
        "infra_test_results",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("result_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("test_id", sa.String(50), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("site_id", sa.String(50), nullable=True),
        sa.Column("device_id", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("detail_json", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("triggered_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── audit_log_entries ───────────────────────────────────────────
    op.create_table(
        "audit_log_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entry_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("target_type", sa.String(100), nullable=True),
        sa.Column("target_id", sa.String(100), nullable=True),
        sa.Column("site_id", sa.String(50), nullable=True),
        sa.Column("device_id", sa.String(50), nullable=True),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("detail_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Device carrier columns ──────────────────────────────────────
    for col_name, col_type, kwargs in [
        ("carrier",            sa.String(50),  {}),
        ("sim_id",             sa.String(50),  {}),
        ("imsi",               sa.String(20),  {}),
        ("network_status",     sa.String(50),  {}),
        ("data_usage_mb",      sa.Float,       {}),
        ("last_network_event", sa.DateTime(timezone=True), {}),
    ]:
        try:
            op.add_column("devices", sa.Column(col_name, col_type, nullable=True, **kwargs))
        except Exception:
            pass

    # ── Site NG911 columns ──────────────────────────────────────────
    for col_name, col_type in [
        ("psap_id",          sa.String(100)),
        ("emergency_class",  sa.String(100)),
        ("ng911_uri",        sa.String(500)),
    ]:
        try:
            op.add_column("sites", sa.Column(col_name, col_type, nullable=True))
        except Exception:
            pass

    # ── Incident category ───────────────────────────────────────────
    try:
        op.add_column("incidents", sa.Column("category", sa.String(50), nullable=True))
    except Exception:
        pass

    # ── Performance indexes ─────────────────────────────────────────
    indexes = [
        ("ix_network_events_tenant_type", "network_events", ["tenant_id", "event_type"]),
        ("ix_network_events_device",      "network_events", ["device_id", "created_at"]),
        ("ix_infra_test_results_test",    "infra_test_results", ["test_id", "created_at"]),
        ("ix_infra_test_results_tenant",  "infra_test_results", ["tenant_id", "status"]),
        ("ix_audit_log_tenant_cat",       "audit_log_entries", ["tenant_id", "category"]),
        ("ix_audit_log_target",           "audit_log_entries", ["target_type", "target_id"]),
        ("ix_incidents_category",         "incidents", ["tenant_id", "category"]),
        ("ix_devices_carrier",            "devices", ["carrier"]),
        ("ix_devices_network_status",     "devices", ["network_status"]),
    ]
    for name, table, cols in indexes:
        try:
            op.create_index(name, table, cols)
        except Exception:
            pass


def downgrade() -> None:
    op.drop_table("audit_log_entries")
    op.drop_table("infra_test_results")
    op.drop_table("infra_tests")
    op.drop_table("network_events")

    for col in ["carrier", "sim_id", "imsi", "network_status", "data_usage_mb", "last_network_event"]:
        try:
            op.drop_column("devices", col)
        except Exception:
            pass
    for col in ["psap_id", "emergency_class", "ng911_uri"]:
        try:
            op.drop_column("sites", col)
        except Exception:
            pass
    try:
        op.drop_column("incidents", "category")
    except Exception:
        pass
