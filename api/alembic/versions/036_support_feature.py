"""Support AI assistant — sessions, messages, diagnostics, escalations, AI summaries.

Revision ID: 036
Revises: 035
Create Date: 2026-04-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── support_sessions ──
    op.create_table(
        "support_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("site_id", sa.Integer, nullable=True),
        sa.Column("device_id", sa.Integer, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("issue_category", sa.String(100), nullable=True),
        sa.Column("resolution_summary", sa.Text, nullable=True),
        sa.Column("escalated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("message_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── support_messages ──
    op.create_table(
        "support_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("support_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("structured_response", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── support_diagnostics ──
    op.create_table(
        "support_diagnostics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("support_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("check_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("customer_safe_summary", sa.Text, nullable=False),
        sa.Column("internal_summary", sa.Text, nullable=False),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── support_escalations ──
    op.create_table(
        "support_escalations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("support_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("probable_cause", sa.Text, nullable=True),
        sa.Column("diagnostics_checked", JSONB, nullable=True),
        sa.Column("recommended_followup", sa.Text, nullable=True),
        sa.Column("handoff_summary", sa.Text, nullable=False),
        sa.Column("zoho_ticket_id", sa.String(100), nullable=True, index=True),
        sa.Column("zoho_ticket_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── support_ai_summaries ──
    op.create_table(
        "support_ai_summaries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("support_sessions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("issue_category", sa.String(100), nullable=True),
        sa.Column("probable_cause", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("diagnostics_run", JSONB, nullable=True),
        sa.Column("recommended_actions", JSONB, nullable=True),
        sa.Column("transcript_summary", sa.Text, nullable=True),
        sa.Column("escalated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("support_ai_summaries")
    op.drop_table("support_escalations")
    op.drop_table("support_diagnostics")
    op.drop_table("support_messages")
    op.drop_table("support_sessions")
