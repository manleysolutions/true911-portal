"""Zoho subscription lifecycle staging tables — Phase 0 scaffolding.

Revision ID: 047
Revises: 046
Create Date: 2026-06-02

Additive only.  Creates three NEW staging/shadow tables so Zoho CRM can become
the System of Record for LIFECYCLE status (a separate axis from operational
status) without ever overwriting sites/devices/lines:

  * ``external_record_map`` — generic mapping of an external CRM record
    (source + module + external_record_id) to optional True911 links.  Broader
    than the existing external_customer_map / external_subscription_map, which
    are left untouched.

  * ``zoho_subscription_records`` — shadow mirror of Zoho Subscription_Mgmt
    records (Subscription Mgmt ID, Account Name, FacilityName, MSISDN, Device
    Activation Status, Connection Type, Subscription Type, MRC, Service Term
    Ends) plus a normalized ``lifecycle_state`` and a sanitized raw_json.

  * ``zoho_payload_observations`` — sanitized, secret-free structural record of
    inbound Zoho webhooks (matched and unmatched) for contract discovery.

All three are guarded by table-existence checks so this migration is idempotent
and safe to re-run on a populated production database.  The downgrade is a clean
drop of only these three new tables.  Nothing here touches any existing column
or table, and the Zoho webhook auth path is unchanged.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


# Index names match the models' inline index=True auto-naming (ix_<table>_<col>)
# so the live schema and ORM metadata agree.
_OBS_INDEXES = (
    "ix_zoho_payload_observations_org_id",
    "ix_zoho_payload_observations_module",
    "ix_zoho_payload_observations_event_type",
)
_SUB_INDEXES = (
    "ix_zoho_subscription_records_subscription_mgmt_id",
    "ix_zoho_subscription_records_msisdn",
)
_RECORD_MAP_INDEXES = ("ix_external_record_map_org_id",)


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "external_record_map" not in existing:
        op.create_table(
            "external_record_map",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("org_id", sa.String(100), nullable=False),
            sa.Column("source", sa.String(50), nullable=False, server_default="zoho_crm"),
            sa.Column("module", sa.String(100), nullable=False),
            sa.Column("external_record_id", sa.String(255), nullable=False),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), nullable=True),
            sa.Column("linked_tenant_id", sa.String(100), nullable=True),
            sa.Column("site_id", sa.String(50), nullable=True),
            sa.Column("device_id", sa.String(50), nullable=True),
            sa.Column("line_id", sa.String(50), nullable=True),
            sa.Column("map_status", sa.String(30), nullable=False, server_default="unmapped"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint(
                "source", "module", "external_record_id",
                name="uq_external_record_map_identity",
            ),
        )
        op.create_index("ix_external_record_map_org_id", "external_record_map", ["org_id"])

    if "zoho_subscription_records" not in existing:
        op.create_table(
            "zoho_subscription_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("org_id", sa.String(100), nullable=False),
            sa.Column("subscription_mgmt_id", sa.String(255), nullable=False),
            sa.Column("account_name", sa.String(255), nullable=True),
            sa.Column("facility_name", sa.String(255), nullable=True),
            sa.Column("msisdn", sa.String(30), nullable=True),
            sa.Column("device_activation_status", sa.String(100), nullable=True),
            sa.Column("connection_type", sa.String(100), nullable=True),
            sa.Column("subscription_type", sa.String(100), nullable=True),
            sa.Column("mrc", sa.Numeric(10, 2), nullable=True),
            sa.Column("service_term_ends", sa.Date(), nullable=True),
            sa.Column("lifecycle_state", sa.String(30), nullable=True),
            sa.Column(
                "external_record_map_id",
                sa.Integer(),
                sa.ForeignKey("external_record_map.id"),
                nullable=True,
            ),
            sa.Column(
                "last_event_id",
                sa.Integer(),
                sa.ForeignKey("integration_events.id"),
                nullable=True,
            ),
            sa.Column("raw_json", JSONB(), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint(
                "org_id", "subscription_mgmt_id",
                name="uq_zoho_subscription_records_identity",
            ),
        )
        op.create_index(
            "ix_zoho_subscription_records_subscription_mgmt_id",
            "zoho_subscription_records", ["subscription_mgmt_id"],
        )
        op.create_index(
            "ix_zoho_subscription_records_msisdn",
            "zoho_subscription_records", ["msisdn"],
        )

    if "zoho_payload_observations" not in existing:
        op.create_table(
            "zoho_payload_observations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("org_id", sa.String(100), nullable=False),
            sa.Column("module", sa.String(100), nullable=True),
            sa.Column("event_type", sa.String(100), nullable=True),
            sa.Column("matched_subscription", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("top_level_keys", JSONB(), nullable=True),
            sa.Column("sanitized_payload", JSONB(), nullable=True),
            sa.Column(
                "integration_event_id",
                sa.Integer(),
                sa.ForeignKey("integration_events.id"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        for ix, col in zip(_OBS_INDEXES, ("org_id", "module", "event_type")):
            op.create_index(ix, "zoho_payload_observations", [col])


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "zoho_payload_observations" in existing:
        for ix in _OBS_INDEXES:
            op.drop_index(ix, table_name="zoho_payload_observations")
        op.drop_table("zoho_payload_observations")

    if "zoho_subscription_records" in existing:
        for ix in _SUB_INDEXES:
            op.drop_index(ix, table_name="zoho_subscription_records")
        op.drop_table("zoho_subscription_records")

    if "external_record_map" in existing:
        for ix in _RECORD_MAP_INDEXES:
            op.drop_index(ix, table_name="external_record_map")
        op.drop_table("external_record_map")
