"""Add site_id column to sims table for direct site-to-SIM assignment.

Revision ID: 026
Revises: 025
"""

from alembic import op
import sqlalchemy as sa

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sims", sa.Column("site_id", sa.String(50), nullable=True, index=True))


def downgrade() -> None:
    op.drop_column("sims", "site_id")
