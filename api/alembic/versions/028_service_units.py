"""Create service_units table for elevator/emergency comms tracking.

Revision ID: 028
Revises: 027
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_units",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("site_id", sa.String(50), nullable=False, index=True),
        sa.Column("unit_id", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("unit_name", sa.String(255), nullable=False),
        sa.Column("unit_type", sa.String(50), nullable=False),
        sa.Column("location_description", sa.String(500), nullable=True),
        sa.Column("floor", sa.String(30), nullable=True),
        sa.Column("install_type", sa.String(30), nullable=True),
        # Communications capabilities
        sa.Column("voice_supported", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("video_supported", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("text_supported", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("visual_messaging_supported", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("onsite_takeover_supported", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("backup_power_supported", sa.Boolean, nullable=False, server_default="false"),
        # Monitoring
        sa.Column("monitoring_station_type", sa.String(100), nullable=True),
        # Compliance
        sa.Column("compliance_status", sa.String(30), nullable=True),
        sa.Column("compliance_notes", sa.Text, nullable=True),
        sa.Column("jurisdiction_code", sa.String(100), nullable=True),
        sa.Column("governing_code_edition", sa.String(100), nullable=True),
        sa.Column("compliance_last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        # Video readiness
        sa.Column("camera_present", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("video_stream_url", sa.String(500), nullable=True),
        sa.Column("video_transport_type", sa.String(50), nullable=True),
        sa.Column("video_encryption", sa.String(50), nullable=True),
        sa.Column("video_retained", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("video_operator_visible", sa.Boolean, nullable=False, server_default="false"),
        # Linkage
        sa.Column("device_id", sa.String(50), nullable=True, index=True),
        sa.Column("line_id", sa.String(50), nullable=True, index=True),
        sa.Column("sim_id", sa.Integer, nullable=True),
        # Status
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        # Metadata
        sa.Column("meta", JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("service_units")
