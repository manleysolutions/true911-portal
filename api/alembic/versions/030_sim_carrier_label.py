"""Add carrier_label to sims — user-defined label from carrier portal.

Revision ID: 030
Revises: 029
"""

from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sims", sa.Column("carrier_label", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("sims", "carrier_label")
