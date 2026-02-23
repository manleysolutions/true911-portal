"""Add iccid and msisdn columns to devices table

Revision ID: 003
Revises: 002
Create Date: 2026-02-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("iccid", sa.String(30), nullable=True))
    op.add_column("devices", sa.Column("msisdn", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "msisdn")
    op.drop_column("devices", "iccid")
