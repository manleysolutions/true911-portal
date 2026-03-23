"""Add line intelligence event log and port state tables.

Revision ID: 034
Revises: 033
Create Date: 2026-03-23

Additive-only migration.  Creates two new tables for the Line
Intelligence Engine.  No existing tables or columns are modified.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "line_intelligence_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event_id", sa.String(50), unique=True, index=True, nullable=False),
        sa.Column("tenant_id", sa.String(100), index=True, nullable=False),
        sa.Column("event_type", sa.String(50), index=True, nullable=False),
        sa.Column("line_id", sa.String(50), index=True, nullable=True),
        sa.Column("device_id", sa.String(50), index=True, nullable=True),
        sa.Column("site_id", sa.String(50), index=True, nullable=True),
        sa.Column("port_index", sa.Integer, nullable=True),
        sa.Column("classified_type", sa.String(30), nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("confidence_tier", sa.String(20), nullable=True),
        sa.Column("profile_id", sa.String(50), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "port_states",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(100), index=True, nullable=False),
        sa.Column("device_id", sa.String(50), index=True, nullable=False),
        sa.Column("line_id", sa.String(50), index=True, nullable=True),
        sa.Column("site_id", sa.String(50), index=True, nullable=True),
        sa.Column("port_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("classified_type", sa.String(30), nullable=False, server_default="unknown"),
        sa.Column("confidence_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("confidence_tier", sa.String(20), nullable=False, server_default="none"),
        sa.Column("profile_id", sa.String(50), nullable=True),
        sa.Column("profile_name", sa.String(100), nullable=True),
        sa.Column("manual_override", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("override_reason", sa.Text, nullable=True),
        sa.Column("last_observation_id", sa.String(50), nullable=True),
        sa.Column("observation_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("port_states")
    op.drop_table("line_intelligence_events")
