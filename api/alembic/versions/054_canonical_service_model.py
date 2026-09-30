"""Canonical Life-Safety Service & Connection model (D-023).

Revision ID: 054
Revises: 053
Create Date: 2026-09-30

Additive only.  Creates eight NEW tables for the canonical model
  Building -> LifeSafetyService -> LifeSafetyConnection -> CommunicationsAsset
plus provenance (canonical_evidence), lifecycle events, projection runs and the
supersedable operator-decision ledger.  Nothing reads them at runtime in
PR #186a; they are written only by the reconciliation writer under an explicit
``--apply``.  Existence-guarded; portable column types (no JSONB) so they also
build on the SQLite test engine.  Downgrade drops only these tables.  Chains off
the single head ``053``.
"""

import sqlalchemy as sa
from alembic import op

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None

_TS = dict(timezone=True)


def _created():
    return sa.Column("created_at", sa.DateTime(**_TS), server_default=sa.func.now())


def _updated():
    return sa.Column("updated_at", sa.DateTime(**_TS), server_default=sa.func.now())


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "projection_runs" not in existing:
        op.create_table(
            "projection_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("mode", sa.String(20), nullable=False),
            sa.Column("run_by", sa.String(255), nullable=False),
            sa.Column("started_at", sa.DateTime(**_TS), nullable=False),
            sa.Column("finished_at", sa.DateTime(**_TS), nullable=True),
            sa.Column("sources", sa.Text(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("degraded", sa.Boolean(), nullable=False, server_default=sa.false()),
            _created(),
        )
        op.create_index("ix_projection_runs_tenant_id", "projection_runs", ["tenant_id"])

    if "communications_assets" not in existing:
        op.create_table(
            "communications_assets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("asset_type", sa.String(30), nullable=False),
            sa.Column("normalized_value", sa.String(120), nullable=False),
            sa.Column("display_value", sa.String(120), nullable=False),
            sa.Column("carrier", sa.String(60), nullable=True),
            sa.Column("lifecycle", sa.String(20), nullable=False, server_default="UNKNOWN"),
            sa.Column("lifecycle_reason", sa.String(60), nullable=True),
            sa.Column("lifecycle_source", sa.String(20), nullable=True),
            sa.Column("effective_from", sa.DateTime(**_TS), nullable=True),
            sa.Column("effective_to", sa.DateTime(**_TS), nullable=True),
            sa.Column("superseded_by_asset_id", sa.Integer(), nullable=True),
            sa.Column("lifecycle_event_id", sa.Integer(), nullable=True),
            sa.Column("building_id", sa.Integer(), nullable=True),
            sa.Column("placement_confidence", sa.String(20), nullable=False,
                      server_default="UNRESOLVED"),
            sa.Column("placement_basis", sa.String(60), nullable=True),
            sa.Column("source", sa.String(20), nullable=True),
            sa.Column("source_record_id", sa.String(120), nullable=True),
            sa.Column("last_projection_run_id", sa.Integer(), nullable=True),
            _created(), _updated(),
            sa.UniqueConstraint("tenant_id", "asset_type", "normalized_value",
                                name="uq_comm_asset_identity"),
        )
        op.create_index("ix_communications_assets_tenant_id", "communications_assets",
                        ["tenant_id"])
        op.create_index("ix_communications_assets_building_id", "communications_assets",
                        ["building_id"])

    if "life_safety_services" not in existing:
        op.create_table(
            "life_safety_services",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("building_id", sa.Integer(), nullable=False),
            sa.Column("service_key", sa.String(160), nullable=False),
            sa.Column("service_type", sa.String(30), nullable=False),
            sa.Column("display_name", sa.String(160), nullable=True),
            sa.Column("confidence", sa.String(20), nullable=False, server_default="UNRESOLVED"),
            sa.Column("approval", sa.String(20), nullable=False, server_default="NONE"),
            sa.Column("approved_by", sa.String(255), nullable=True),
            sa.Column("approved_at", sa.DateTime(**_TS), nullable=True),
            sa.Column("lifecycle", sa.String(20), nullable=False, server_default="UNKNOWN"),
            sa.Column("lifecycle_reason", sa.String(60), nullable=True),
            sa.Column("source_summary", sa.Text(), nullable=True),
            sa.Column("legacy_service_unit_id", sa.String(50), nullable=True),
            sa.Column("last_projection_run_id", sa.Integer(), nullable=True),
            _created(), _updated(),
            sa.UniqueConstraint("tenant_id", "building_id", "service_key",
                                name="uq_ls_service_key"),
        )
        op.create_index("ix_life_safety_services_tenant_id", "life_safety_services",
                        ["tenant_id"])
        op.create_index("ix_life_safety_services_building_id", "life_safety_services",
                        ["building_id"])
        op.create_index("ix_ls_services_tenant_building", "life_safety_services",
                        ["tenant_id", "building_id"])

    if "life_safety_connections" not in existing:
        op.create_table(
            "life_safety_connections",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("service_id", sa.Integer(), nullable=False),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("connection_type", sa.String(30), nullable=False),
            sa.Column("requirement", sa.String(20), nullable=False, server_default="REQUIRED"),
            sa.Column("provisioning", sa.String(20), nullable=False,
                      server_default="NO_ASSET_LINKED"),
            sa.Column("confidence", sa.String(20), nullable=False, server_default="CONFIRMED"),
            sa.Column("last_projection_run_id", sa.Integer(), nullable=True),
            _created(), _updated(),
            sa.UniqueConstraint("service_id", "ordinal", name="uq_ls_connection_ordinal"),
        )
        op.create_index("ix_life_safety_connections_tenant_id", "life_safety_connections",
                        ["tenant_id"])
        op.create_index("ix_life_safety_connections_service_id", "life_safety_connections",
                        ["service_id"])

    if "connection_asset_links" not in existing:
        op.create_table(
            "connection_asset_links",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("connection_id", sa.Integer(), nullable=False),
            sa.Column("asset_id", sa.Integer(), nullable=False),
            sa.Column("relationship", sa.String(30), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            _created(),
            sa.UniqueConstraint("connection_id", "asset_id", "relationship",
                                name="uq_conn_asset_link"),
        )
        op.create_index("ix_connection_asset_links_tenant_id", "connection_asset_links",
                        ["tenant_id"])
        op.create_index("ix_connection_asset_links_connection_id", "connection_asset_links",
                        ["connection_id"])
        op.create_index("ix_connection_asset_links_asset_id", "connection_asset_links",
                        ["asset_id"])

    if "asset_lifecycle_events" not in existing:
        op.create_table(
            "asset_lifecycle_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("building_id", sa.Integer(), nullable=True),
            sa.Column("event_type", sa.String(30), nullable=False),
            sa.Column("effective_at", sa.DateTime(**_TS), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("source", sa.String(20), nullable=False, server_default="OPERATOR"),
            sa.Column("operator_decision_id", sa.Integer(), nullable=True, unique=True),
            _created(),
        )
        op.create_index("ix_asset_lifecycle_events_tenant_id", "asset_lifecycle_events",
                        ["tenant_id"])

    if "canonical_evidence" not in existing:
        op.create_table(
            "canonical_evidence",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("projection_run_id", sa.Integer(), nullable=False),
            sa.Column("subject_type", sa.String(20), nullable=False),
            sa.Column("subject_key", sa.String(200), nullable=False),
            sa.Column("source", sa.String(20), nullable=False),
            sa.Column("source_record_id", sa.String(120), nullable=True),
            sa.Column("evidence_type", sa.String(60), nullable=False),
            sa.Column("confidence", sa.String(20), nullable=True),
            sa.Column("observed_at", sa.DateTime(**_TS), nullable=True),
            sa.Column("payload", sa.Text(), nullable=True),
            _created(),
        )
        op.create_index("ix_canonical_evidence_tenant_id", "canonical_evidence", ["tenant_id"])
        op.create_index("ix_canonical_evidence_projection_run_id", "canonical_evidence",
                        ["projection_run_id"])
        op.create_index("ix_canon_evidence_subject", "canonical_evidence",
                        ["tenant_id", "subject_type", "subject_key"])

    if "operator_decisions" not in existing:
        op.create_table(
            "operator_decisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("decision_type", sa.String(40), nullable=False),
            sa.Column("decision_key", sa.String(200), nullable=False),
            sa.Column("subject", sa.Text(), nullable=False),
            sa.Column("previous_state", sa.Text(), nullable=True),
            sa.Column("new_state", sa.Text(), nullable=False),
            sa.Column("effective_date", sa.DateTime(**_TS), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("source", sa.String(20), nullable=False, server_default="OPERATOR"),
            sa.Column("recorded_by", sa.String(255), nullable=False),
            sa.Column("recorded_at", sa.DateTime(**_TS), nullable=False),
            sa.Column("input_fingerprint", sa.String(64), nullable=True),
            sa.Column("superseded_by_id", sa.Integer(), nullable=True),
            sa.Column("superseded_at", sa.DateTime(**_TS), nullable=True),
            _created(),
        )
        op.create_index("ix_operator_decisions_tenant_id", "operator_decisions", ["tenant_id"])
        op.create_index("ix_operator_decisions_decision_key", "operator_decisions",
                        ["decision_key"])
        op.create_index("ix_operator_decisions_active", "operator_decisions",
                        ["tenant_id", "decision_key", "superseded_by_id"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for table in ("operator_decisions", "canonical_evidence", "asset_lifecycle_events",
                  "connection_asset_links", "life_safety_connections",
                  "life_safety_services", "communications_assets", "projection_runs"):
        if table in existing:
            op.drop_table(table)
