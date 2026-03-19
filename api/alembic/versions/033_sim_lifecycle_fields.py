"""Add SIM lifecycle fields: reconciliation_status, last_seen_at, customer_id.

Revision ID: 033
Revises: 032
"""

from alembic import op
import sqlalchemy as sa

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sims", sa.Column("reconciliation_status", sa.String(20), nullable=True, server_default="unverified"))
    op.add_column("sims", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sims", sa.Column("customer_id", sa.Integer(), nullable=True))
    op.create_index("ix_sims_customer_id", "sims", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_sims_customer_id", "sims")
    op.drop_column("sims", "customer_id")
    op.drop_column("sims", "last_seen_at")
    op.drop_column("sims", "reconciliation_status")
