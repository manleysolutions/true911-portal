"""Create provisioning_queue table for agent-driven site provisioning.

Revision ID: 029
Revises: 028
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provisioning_queue",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("item_type", sa.String(30), nullable=False, index=True),
        sa.Column("item_id", sa.Integer, nullable=False, index=True),
        sa.Column("external_ref", sa.String(100), nullable=True),
        sa.Column("source_provider", sa.String(50), nullable=True),
        sa.Column("source_sync_id", sa.String(100), nullable=True),
        sa.Column("current_site_id", sa.String(50), nullable=True),
        sa.Column("current_device_id", sa.String(50), nullable=True),
        sa.Column("suggested_tenant_id", sa.String(100), nullable=True),
        sa.Column("suggested_site_id", sa.String(50), nullable=True),
        sa.Column("suggested_site_name", sa.String(255), nullable=True),
        sa.Column("suggested_device_id", sa.String(50), nullable=True),
        sa.Column("suggested_unit_type", sa.String(50), nullable=True),
        sa.Column("suggestion_confidence", sa.Float, nullable=True),
        sa.Column("suggestion_reason", sa.String(500), nullable=True),
        sa.Column("missing_e911", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("missing_site", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("missing_customer", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("needs_compliance_review", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("status", sa.String(30), nullable=False, server_default="new", index=True),
        sa.Column("resolved_by", sa.String(255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_site_id", sa.String(50), nullable=True),
        sa.Column("meta", JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_pq_type_status", "provisioning_queue", ["item_type", "status"])


def downgrade() -> None:
    op.drop_index("ix_pq_type_status", table_name="provisioning_queue")
    op.drop_table("provisioning_queue")
