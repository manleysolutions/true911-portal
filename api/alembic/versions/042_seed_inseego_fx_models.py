"""Seed Inseego FX-series cellular gateways into the hardware catalog.

Revision ID: 042
Revises: 041
Create Date: 2026-05-22

Data migration — additive only.  Adds the Inseego FX3100 and FX3110
fixed-wireless gateways to ``hardware_models`` so they appear in the
device-registration dropdown in production.  (The demo seed in
``seed.py`` only runs in demo mode, so production needs the rows
inserted by a migration — same pattern as migration 024.)

The existing catalog (migration 024) carries the Inseego FW3100 only;
the FX-series is a separate Inseego product line used for managed POTS
replacement deployments (e.g. Red Tag Line).

Each row is inserted only when absent, so this migration is safe to
re-run and will not disturb a catalog row already present.
"""

import sqlalchemy as sa
from alembic import op

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None

# (id, manufacturer, model_name, device_type)
HARDWARE_MODELS = [
    ("inseego-fx3100", "Inseego", "Inseego FX3100", "Cellular Router"),
    ("inseego-fx3110", "Inseego", "Inseego FX3110", "Cellular Router"),
]


def upgrade() -> None:
    tbl = sa.table(
        "hardware_models",
        sa.column("id", sa.String),
        sa.column("manufacturer", sa.String),
        sa.column("model_name", sa.String),
        sa.column("device_type", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    conn = op.get_bind()
    for mid, mfr, name, dtype in HARDWARE_MODELS:
        exists = conn.execute(
            sa.text("SELECT 1 FROM hardware_models WHERE id = :id"),
            {"id": mid},
        ).fetchone()
        if not exists:
            conn.execute(
                tbl.insert().values(
                    id=mid,
                    manufacturer=mfr,
                    model_name=name,
                    device_type=dtype,
                    is_active=True,
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    for mid, _, _, _ in HARDWARE_MODELS:
        conn.execute(
            sa.text("DELETE FROM hardware_models WHERE id = :id"),
            {"id": mid},
        )
