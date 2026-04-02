"""Self-healing remediation actions table.

Revision ID: 038
Revises: 037
Create Date: 2026-04-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_remediation_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("support_sessions.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("escalation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("site_id", sa.Integer, nullable=True),
        sa.Column("device_id", sa.Integer, nullable=True),
        sa.Column("issue_category", sa.String(100), nullable=True),
        sa.Column("trigger_source", sa.String(50), nullable=False),
        sa.Column("action_type", sa.String(80), nullable=False),
        sa.Column("action_level", sa.String(20), nullable=False, server_default="safe"),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_status", sa.String(30), nullable=True),
        sa.Column("verification_summary", sa.Text, nullable=True),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("blocked_reason", sa.Text, nullable=True),
        sa.Column("raw_result", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("support_remediation_actions")
