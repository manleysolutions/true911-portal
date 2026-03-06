"""018 – Autonomous Infrastructure Operations (Phase 8)

New tables:
  - autonomous_actions      Log of all autonomous platform actions
  - operational_digests     Generated operational summary reports

Column additions:
  - automation_rules: max_fires_per_hour, cooldown_minutes, auto_diagnostic, self_heal_action
  - escalation_rules: tier, notify_email, notify_sms, auto_assign_vendor

Performance indexes.
"""

from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── autonomous_actions ──────────────────────────────────────────
    op.create_table(
        "autonomous_actions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("action_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("trigger_source", sa.String(100), nullable=False),
        sa.Column("site_id", sa.String(50), nullable=True, index=True),
        sa.Column("device_id", sa.String(50), nullable=True),
        sa.Column("incident_id", sa.String(50), nullable=True),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("detail_json", sa.Text, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="completed"),
        sa.Column("result", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── operational_digests ─────────────────────────────────────────
    op.create_table(
        "operational_digests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("digest_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("digest_type", sa.String(30), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── automation_rules extensions ─────────────────────────────────
    for col_name, col_type, kwargs in [
        ("max_fires_per_hour", sa.Integer, {"server_default": "10"}),
        ("cooldown_minutes", sa.Integer, {"server_default": "15"}),
        ("auto_diagnostic", sa.String(100), {}),
        ("self_heal_action", sa.String(100), {}),
    ]:
        try:
            op.add_column("automation_rules", sa.Column(col_name, col_type, nullable=True, **kwargs))
        except Exception:
            pass

    # ── escalation_rules extensions ─────────────────────────────────
    for col_name, col_type in [
        ("tier", sa.Integer),
        ("notify_email", sa.String(255)),
        ("notify_sms", sa.String(50)),
        ("auto_assign_vendor", sa.Boolean),
    ]:
        try:
            op.add_column("escalation_rules", sa.Column(col_name, col_type, nullable=True))
        except Exception:
            pass

    # ── Performance indexes ─────────────────────────────────────────
    indexes = [
        ("ix_auto_actions_tenant_type", "autonomous_actions", ["tenant_id", "action_type"]),
        ("ix_auto_actions_created", "autonomous_actions", ["tenant_id", "created_at"]),
        ("ix_auto_actions_site", "autonomous_actions", ["site_id", "created_at"]),
        ("ix_op_digests_tenant_type", "operational_digests", ["tenant_id", "digest_type"]),
        ("ix_op_digests_period", "operational_digests", ["tenant_id", "period_start"]),
    ]
    for name, table, cols in indexes:
        try:
            op.create_index(name, table, cols)
        except Exception:
            pass


def downgrade() -> None:
    op.drop_table("operational_digests")
    op.drop_table("autonomous_actions")
    for col in ["max_fires_per_hour", "cooldown_minutes", "auto_diagnostic", "self_heal_action"]:
        try:
            op.drop_column("automation_rules", col)
        except Exception:
            pass
    for col in ["tier", "notify_email", "notify_sms", "auto_assign_vendor"]:
        try:
            op.drop_column("escalation_rules", col)
        except Exception:
            pass
