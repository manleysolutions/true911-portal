"""Add manufacturer, activated_at, term_end_date to devices.

Revision ID: 020
Revises: 019
"""

from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"


def upgrade() -> None:
    op.add_column("devices", sa.Column("manufacturer", sa.String(100), nullable=True))
    op.add_column("devices", sa.Column("activated_at", sa.Date, nullable=True))
    op.add_column("devices", sa.Column("term_end_date", sa.Date, nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "term_end_date")
    op.drop_column("devices", "activated_at")
    op.drop_column("devices", "manufacturer")
