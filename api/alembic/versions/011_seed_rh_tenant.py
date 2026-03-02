"""Seed 'rh' tenant (Restoration Hardware).

Revision ID: 011
Revises: 010
Create Date: 2026-03-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tenants = sa.table(
        "tenants",
        sa.column("tenant_id", sa.String),
        sa.column("name", sa.String),
    )
    # Insert only if not already present
    conn = op.get_bind()
    exists = conn.execute(
        sa.select(tenants.c.tenant_id).where(tenants.c.tenant_id == "rh")
    ).first()
    if not exists:
        op.execute(
            tenants.insert().values(tenant_id="rh", name="Restoration Hardware")
        )


def downgrade() -> None:
    tenants = sa.table("tenants", sa.column("tenant_id", sa.String))
    op.execute(tenants.delete().where(tenants.c.tenant_id == "rh"))
