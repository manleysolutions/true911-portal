"""Add acting_as_tenant_id and original_tenant_id to action_audits.

Revision ID: 012
Revises: 011
Create Date: 2026-03-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "action_audits",
        sa.Column("acting_as_tenant_id", sa.String(100), nullable=True),
    )
    op.add_column(
        "action_audits",
        sa.Column("original_tenant_id", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("action_audits", "original_tenant_id")
    op.drop_column("action_audits", "acting_as_tenant_id")
