"""Add api_key_hash, claimed_at, claimed_by to devices

Revision ID: 005
Revises: 004
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("api_key_hash", sa.String(128), nullable=True))
    op.add_column("devices", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("claimed_by", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "claimed_by")
    op.drop_column("devices", "claimed_at")
    op.drop_column("devices", "api_key_hash")
