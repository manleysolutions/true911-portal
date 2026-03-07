"""Widen e911_state and other tight string columns.

Revision ID: 021
Revises: 020
"""

from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"


def upgrade() -> None:
    op.alter_column("sites", "e911_state", type_=sa.String(50), existing_nullable=True)
    op.alter_column("sites", "e911_zip", type_=sa.String(30), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("sites", "e911_zip", type_=sa.String(20), existing_nullable=True)
    op.alter_column("sites", "e911_state", type_=sa.String(10), existing_nullable=True)
