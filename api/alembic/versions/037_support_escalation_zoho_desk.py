"""Add Zoho Desk integration and deduplication fields to support_escalations.

Revision ID: 037
Revises: 036
Create Date: 2026-04-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New columns on support_escalations
    op.add_column("support_escalations", sa.Column("site_id", sa.Integer, nullable=True))
    op.add_column("support_escalations", sa.Column("device_id", sa.Integer, nullable=True))
    op.add_column("support_escalations", sa.Column("issue_category", sa.String(100), nullable=True))
    op.add_column("support_escalations", sa.Column("escalation_level", sa.String(30), nullable=True))
    op.add_column("support_escalations", sa.Column("zoho_ticket_number", sa.String(50), nullable=True))
    op.add_column("support_escalations", sa.Column("zoho_status", sa.String(50), nullable=True))
    op.add_column("support_escalations", sa.Column("dedupe_key", sa.String(255), nullable=True, index=True))
    op.add_column("support_escalations", sa.Column("was_deduplicated", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("support_escalations", sa.Column("linked_escalation_id", UUID(as_uuid=True), nullable=True))
    op.add_column("support_escalations", sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("support_escalations", sa.Column("sync_error", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("support_escalations", "sync_error")
    op.drop_column("support_escalations", "synced_at")
    op.drop_column("support_escalations", "linked_escalation_id")
    op.drop_column("support_escalations", "was_deduplicated")
    op.drop_column("support_escalations", "dedupe_key")
    op.drop_column("support_escalations", "zoho_status")
    op.drop_column("support_escalations", "zoho_ticket_number")
    op.drop_column("support_escalations", "escalation_level")
    op.drop_column("support_escalations", "issue_category")
    op.drop_column("support_escalations", "device_id")
    op.drop_column("support_escalations", "site_id")
