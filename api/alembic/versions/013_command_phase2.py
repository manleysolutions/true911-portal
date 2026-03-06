"""Command Phase 2: extend incidents, add command_activities table.

Revision ID: 013
Revises: 012
Create Date: 2026-03-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Extend incidents table ---
    op.add_column("incidents", sa.Column("incident_type", sa.String(100), nullable=True))
    op.add_column("incidents", sa.Column("source", sa.String(100), nullable=True))
    op.add_column("incidents", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("location_detail", sa.String(255), nullable=True))
    op.add_column("incidents", sa.Column("recommended_actions_json", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("metadata_json", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))

    # --- Create command_activities table ---
    op.create_table(
        "command_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("activity_type", sa.String(50), nullable=False),
        sa.Column("site_id", sa.String(50), nullable=True, index=True),
        sa.Column("incident_id", sa.String(50), nullable=True),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("command_activities")
    op.drop_column("incidents", "resolved_at")
    op.drop_column("incidents", "metadata_json")
    op.drop_column("incidents", "recommended_actions_json")
    op.drop_column("incidents", "location_detail")
    op.drop_column("incidents", "description")
    op.drop_column("incidents", "source")
    op.drop_column("incidents", "incident_type")
