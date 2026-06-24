"""Ops Center Phase 1.5 — operational-intelligence foundation tables.

Revision ID: 049
Revises: 048
Create Date: 2026-06-24

Additive only.  Creates four NEW, currently-inert tables that scaffold richer
Tier-1 support (escalation queue, knowledge articles, playbooks, learned
resolution patterns).  Nothing reads them at runtime yet, and the whole Ops
Center module self-gates on FEATURE_OPS_CENTER (default off), so this is a
no-op deploy.  Existence-guarded for idempotency; clean drop on downgrade.
Nothing here touches an existing column or table.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "ops_escalation_queue" not in existing:
        op.create_table(
            "ops_escalation_queue",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=True),
            sa.Column("session_id", UUID(as_uuid=True), nullable=True),
            sa.Column("session_ref", sa.String(40), nullable=True),
            sa.Column("issue_category", sa.String(60), nullable=True),
            sa.Column("severity", sa.String(20), nullable=False, server_default="moderate"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
            sa.Column("is_emergency", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("assigned_to", sa.String(255), nullable=True),
            sa.Column("handoff_number", sa.String(40), nullable=True),
            sa.Column("incident_ref", sa.String(50), nullable=True),
            sa.Column("site_id", sa.String(50), nullable=True),
            sa.Column("device_id", sa.String(50), nullable=True),
            sa.Column("meta", JSONB(), nullable=True),
            sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_ops_escalation_queue_tenant_id", "ops_escalation_queue", ["tenant_id"])
        op.create_index("ix_ops_escalation_queue_session_id", "ops_escalation_queue", ["session_id"])

    if "ops_knowledge_articles" not in existing:
        op.create_table(
            "ops_knowledge_articles",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=True),
            sa.Column("slug", sa.String(160), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("issue_category", sa.String(60), nullable=True),
            sa.Column("tags", JSONB(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("created_by", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "slug", name="uq_ops_knowledge_tenant_slug"),
        )
        op.create_index("ix_ops_knowledge_articles_tenant_id", "ops_knowledge_articles", ["tenant_id"])
        op.create_index("ix_ops_knowledge_articles_slug", "ops_knowledge_articles", ["slug"])

    if "ops_playbooks" not in existing:
        op.create_table(
            "ops_playbooks",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=True),
            sa.Column("slug", sa.String(160), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("issue_category", sa.String(60), nullable=True),
            sa.Column("steps", JSONB(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("created_by", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "slug", name="uq_ops_playbook_tenant_slug"),
        )
        op.create_index("ix_ops_playbooks_tenant_id", "ops_playbooks", ["tenant_id"])
        op.create_index("ix_ops_playbooks_slug", "ops_playbooks", ["slug"])

    if "ops_resolution_patterns" not in existing:
        op.create_table(
            "ops_resolution_patterns",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=True),
            sa.Column("issue_category", sa.String(60), nullable=True),
            sa.Column("signature", sa.String(255), nullable=False),
            sa.Column("recommended_action", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
            sa.Column("occurrences", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="candidate"),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "issue_category", "signature", name="uq_ops_resolution_signature"),
        )
        op.create_index("ix_ops_resolution_patterns_tenant_id", "ops_resolution_patterns", ["tenant_id"])
        op.create_index("ix_ops_resolution_patterns_signature", "ops_resolution_patterns", ["signature"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "ops_resolution_patterns" in existing:
        op.drop_index("ix_ops_resolution_patterns_signature", table_name="ops_resolution_patterns")
        op.drop_index("ix_ops_resolution_patterns_tenant_id", table_name="ops_resolution_patterns")
        op.drop_table("ops_resolution_patterns")

    if "ops_playbooks" in existing:
        op.drop_index("ix_ops_playbooks_slug", table_name="ops_playbooks")
        op.drop_index("ix_ops_playbooks_tenant_id", table_name="ops_playbooks")
        op.drop_table("ops_playbooks")

    if "ops_knowledge_articles" in existing:
        op.drop_index("ix_ops_knowledge_articles_slug", table_name="ops_knowledge_articles")
        op.drop_index("ix_ops_knowledge_articles_tenant_id", table_name="ops_knowledge_articles")
        op.drop_table("ops_knowledge_articles")

    if "ops_escalation_queue" in existing:
        op.drop_index("ix_ops_escalation_queue_session_id", table_name="ops_escalation_queue")
        op.drop_index("ix_ops_escalation_queue_tenant_id", table_name="ops_escalation_queue")
        op.drop_table("ops_escalation_queue")
