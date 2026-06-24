"""AI Customer Operations Center / Support Center tables.

Revision ID: 048
Revises: 047
Create Date: 2026-06-24

Additive only.  Creates four NEW tables backing the caller-facing Tier-1
support workflow.  Nothing here touches an existing column or table, and
every /api/ops-center route self-gates on FEATURE_OPS_CENTER (default
off), so this migration is a no-op for runtime behavior until the flag is
enabled:

  * ``asset_identities``     — real-world identifier → asset index so a
                               caller without an account number can be
                               matched (elevator phone number, MSISDN,
                               Napco radio number, ICCID, Starlink ID,
                               site/building name, …).
  * ``ops_support_sessions`` — a temporary caller support session.
  * ``ops_otp_challenges``   — SMS OTP challenges (hashed code only).
  * ``ops_session_events``   — append-only per-session audit trail.

All four are guarded by table-existence checks so the migration is
idempotent and safe to re-run on a populated production database.  The
downgrade is a clean drop of only these four new tables.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "asset_identities" not in existing:
        op.create_table(
            "asset_identities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("identifier_type", sa.String(50), nullable=False),
            sa.Column("identifier_value", sa.String(255), nullable=False),
            sa.Column("identifier_value_normalized", sa.String(255), nullable=False),
            sa.Column("asset_kind", sa.String(30), nullable=False),
            sa.Column("asset_ref", sa.String(100), nullable=False),
            sa.Column("site_id", sa.String(50), nullable=True),
            sa.Column("device_id", sa.String(50), nullable=True),
            sa.Column("service_unit_id", sa.String(50), nullable=True),
            sa.Column("label", sa.String(255), nullable=True),
            sa.Column("category", sa.String(50), nullable=True),
            sa.Column("source", sa.String(50), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("meta", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint(
                "tenant_id",
                "identifier_type",
                "identifier_value_normalized",
                name="uq_asset_identity_tenant_type_value",
            ),
        )
        op.create_index("ix_asset_identities_tenant_id", "asset_identities", ["tenant_id"])
        op.create_index("ix_asset_identities_identifier_type", "asset_identities", ["identifier_type"])
        op.create_index(
            "ix_asset_identities_identifier_value_normalized",
            "asset_identities",
            ["identifier_value_normalized"],
        )
        op.create_index("ix_asset_identities_site_id", "asset_identities", ["site_id"])
        op.create_index("ix_asset_identities_device_id", "asset_identities", ["device_id"])
        op.create_index(
            "ix_asset_identities_type_value",
            "asset_identities",
            ["identifier_type", "identifier_value_normalized"],
        )

    if "ops_support_sessions" not in existing:
        op.create_table(
            "ops_support_sessions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("session_ref", sa.String(40), nullable=False),
            sa.Column("caller_phone", sa.String(40), nullable=True),
            sa.Column("caller_phone_normalized", sa.String(40), nullable=True),
            sa.Column("source", sa.String(30), nullable=False, server_default="phone"),
            sa.Column("issue_category", sa.String(60), nullable=True),
            sa.Column("issue_summary", sa.Text(), nullable=True),
            sa.Column("is_emergency", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("status", sa.String(30), nullable=False, server_default="open"),
            sa.Column("verification_status", sa.String(30), nullable=False, server_default="unverified"),
            sa.Column("matched_tenant_id", sa.String(100), nullable=True),
            sa.Column("matched_site_id", sa.String(50), nullable=True),
            sa.Column("matched_device_id", sa.String(50), nullable=True),
            sa.Column("matched_service_unit_id", sa.String(50), nullable=True),
            sa.Column("matched_asset_identity_id", sa.Integer(), nullable=True),
            sa.Column("matched_asset_kind", sa.String(30), nullable=True),
            sa.Column("matched_label", sa.String(255), nullable=True),
            sa.Column("contact_name", sa.String(255), nullable=True),
            sa.Column("contact_phone_masked", sa.String(40), nullable=True),
            sa.Column("escalation_status", sa.String(30), nullable=False, server_default="none"),
            sa.Column("handoff_number", sa.String(40), nullable=True),
            sa.Column("incident_ref", sa.String(50), nullable=True),
            sa.Column("ticket_ref", sa.String(100), nullable=True),
            sa.Column("opened_by_user_id", UUID(as_uuid=True), nullable=True),
            sa.Column("opened_by_email", sa.String(255), nullable=True),
            sa.Column("opened_by_tenant_id", sa.String(100), nullable=True),
            sa.Column("meta", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_ops_support_sessions_session_ref", "ops_support_sessions", ["session_ref"], unique=True)
        op.create_index("ix_ops_support_sessions_caller_phone_normalized", "ops_support_sessions", ["caller_phone_normalized"])
        op.create_index("ix_ops_support_sessions_matched_tenant_id", "ops_support_sessions", ["matched_tenant_id"])

    if "ops_otp_challenges" not in existing:
        op.create_table(
            "ops_otp_challenges",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "session_id",
                UUID(as_uuid=True),
                sa.ForeignKey("ops_support_sessions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("tenant_id", sa.String(100), nullable=True),
            sa.Column("destination_masked", sa.String(40), nullable=False),
            sa.Column("destination_hash", sa.String(128), nullable=True),
            sa.Column("code_hash", sa.String(128), nullable=False),
            sa.Column("provider", sa.String(40), nullable=False),
            sa.Column("provider_message_id", sa.String(120), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="sent"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_ops_otp_challenges_session_id", "ops_otp_challenges", ["session_id"])
        op.create_index("ix_ops_otp_challenges_tenant_id", "ops_otp_challenges", ["tenant_id"])

    if "ops_session_events" not in existing:
        op.create_table(
            "ops_session_events",
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column(
                "session_id",
                UUID(as_uuid=True),
                sa.ForeignKey("ops_support_sessions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("tenant_id", sa.String(100), nullable=True),
            sa.Column("event_type", sa.String(50), nullable=False),
            sa.Column("actor", sa.String(255), nullable=True),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("detail", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_ops_session_events_session_id", "ops_session_events", ["session_id"])
        op.create_index("ix_ops_session_events_tenant_id", "ops_session_events", ["tenant_id"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "ops_session_events" in existing:
        op.drop_index("ix_ops_session_events_tenant_id", table_name="ops_session_events")
        op.drop_index("ix_ops_session_events_session_id", table_name="ops_session_events")
        op.drop_table("ops_session_events")

    if "ops_otp_challenges" in existing:
        op.drop_index("ix_ops_otp_challenges_tenant_id", table_name="ops_otp_challenges")
        op.drop_index("ix_ops_otp_challenges_session_id", table_name="ops_otp_challenges")
        op.drop_table("ops_otp_challenges")

    if "ops_support_sessions" in existing:
        op.drop_index("ix_ops_support_sessions_matched_tenant_id", table_name="ops_support_sessions")
        op.drop_index("ix_ops_support_sessions_caller_phone_normalized", table_name="ops_support_sessions")
        op.drop_index("ix_ops_support_sessions_session_ref", table_name="ops_support_sessions")
        op.drop_table("ops_support_sessions")

    if "asset_identities" in existing:
        for ix in (
            "ix_asset_identities_type_value",
            "ix_asset_identities_device_id",
            "ix_asset_identities_site_id",
            "ix_asset_identities_identifier_value_normalized",
            "ix_asset_identities_identifier_type",
            "ix_asset_identities_tenant_id",
        ):
            op.drop_index(ix, table_name="asset_identities")
        op.drop_table("asset_identities")
