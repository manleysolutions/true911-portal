"""Ops Center Phase 1.6 — Resolution Intelligence foundation tables.

Revision ID: 052
Revises: 051
Create Date: 2026-06-24

Additive only.  Creates four NEW, currently-inert tables that persist the
structured operational-knowledge library (known issues, diagnostic workflows,
resolution workflows, resolution outcomes).  Nothing reads them at runtime yet,
and the whole Ops Center module self-gates on FEATURE_OPS_CENTER (default off),
so this is a no-op deploy.  Existence-guarded for idempotency; clean drop on
downgrade.  Nothing here touches an existing column or table.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "ops_known_issues" not in existing:
        op.create_table(
            "ops_known_issues",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(80), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("category", sa.String(60), nullable=False),
            sa.Column("severity", sa.String(20), nullable=False, server_default="moderate"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("symptoms", JSONB(), nullable=True),
            sa.Column("probable_causes", JSONB(), nullable=True),
            sa.Column("vendor", sa.String(60), nullable=True),
            sa.Column("carrier", sa.String(60), nullable=True),
            sa.Column("hardware_model", sa.String(100), nullable=True),
            sa.Column("escalation_queue", sa.String(40), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_ops_known_issues_code", "ops_known_issues", ["code"], unique=True)
        op.create_index("ix_ops_known_issues_category", "ops_known_issues", ["category"])
        op.create_index("ix_ops_known_issues_vendor", "ops_known_issues", ["vendor"])
        op.create_index("ix_ops_known_issues_carrier", "ops_known_issues", ["carrier"])
        op.create_index("ix_ops_known_issues_hardware_model", "ops_known_issues", ["hardware_model"])

    if "ops_diagnostic_workflows" not in existing:
        op.create_table(
            "ops_diagnostic_workflows",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(80), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("issue_code", sa.String(80), nullable=True),
            sa.Column("issue_id", UUID(as_uuid=True), nullable=True),
            sa.Column("category", sa.String(60), nullable=True),
            sa.Column("ordered_steps", JSONB(), nullable=True),
            sa.Column("expected_results", JSONB(), nullable=True),
            sa.Column("failure_paths", JSONB(), nullable=True),
            sa.Column("escalation_queue", sa.String(40), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_ops_diagnostic_workflows_code", "ops_diagnostic_workflows", ["code"], unique=True)
        op.create_index("ix_ops_diagnostic_workflows_issue_code", "ops_diagnostic_workflows", ["issue_code"])

    if "ops_resolution_workflows" not in existing:
        op.create_table(
            "ops_resolution_workflows",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(80), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("issue_code", sa.String(80), nullable=True),
            sa.Column("issue_id", UUID(as_uuid=True), nullable=True),
            sa.Column("resolution_steps", JSONB(), nullable=True),
            sa.Column("estimated_time_minutes", sa.Integer(), nullable=True),
            sa.Column("escalation_trigger", sa.Text(), nullable=True),
            sa.Column("success_criteria", JSONB(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_ops_resolution_workflows_code", "ops_resolution_workflows", ["code"], unique=True)
        op.create_index("ix_ops_resolution_workflows_issue_code", "ops_resolution_workflows", ["issue_code"])

    if "ops_resolution_outcomes" not in existing:
        op.create_table(
            "ops_resolution_outcomes",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=True),
            sa.Column("issue_code", sa.String(80), nullable=True),
            sa.Column("issue_id", UUID(as_uuid=True), nullable=True),
            sa.Column("workflow_id", UUID(as_uuid=True), nullable=True),
            sa.Column("workflow_code", sa.String(80), nullable=True),
            sa.Column("session_ref", sa.String(40), nullable=True),
            sa.Column("outcome_type", sa.String(40), nullable=False),
            sa.Column("resolution_notes", sa.Text(), nullable=True),
            sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_ops_resolution_outcomes_tenant_id", "ops_resolution_outcomes", ["tenant_id"])
        op.create_index("ix_ops_resolution_outcomes_issue_code", "ops_resolution_outcomes", ["issue_code"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "ops_resolution_outcomes" in existing:
        op.drop_index("ix_ops_resolution_outcomes_issue_code", table_name="ops_resolution_outcomes")
        op.drop_index("ix_ops_resolution_outcomes_tenant_id", table_name="ops_resolution_outcomes")
        op.drop_table("ops_resolution_outcomes")

    if "ops_resolution_workflows" in existing:
        op.drop_index("ix_ops_resolution_workflows_issue_code", table_name="ops_resolution_workflows")
        op.drop_index("ix_ops_resolution_workflows_code", table_name="ops_resolution_workflows")
        op.drop_table("ops_resolution_workflows")

    if "ops_diagnostic_workflows" in existing:
        op.drop_index("ix_ops_diagnostic_workflows_issue_code", table_name="ops_diagnostic_workflows")
        op.drop_index("ix_ops_diagnostic_workflows_code", table_name="ops_diagnostic_workflows")
        op.drop_table("ops_diagnostic_workflows")

    if "ops_known_issues" in existing:
        for ix in (
            "ix_ops_known_issues_hardware_model",
            "ix_ops_known_issues_carrier",
            "ix_ops_known_issues_vendor",
            "ix_ops_known_issues_category",
            "ix_ops_known_issues_code",
        ):
            op.drop_index(ix, table_name="ops_known_issues")
        op.drop_table("ops_known_issues")
