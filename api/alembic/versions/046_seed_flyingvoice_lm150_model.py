"""Seed the FlyingVoice LM150 VoLTE endpoint into the hardware catalog.

Revision ID: 046
Revises: 045
Create Date: 2026-06-01

Data migration — additive only.  Adds the FlyingVoice (Vola) LM150 VoLTE
ATA / elevator-phone endpoint to ``hardware_models`` so it appears in the
device-registration dropdown in production.  (The demo seed in
``seed.py`` only runs in demo mode, so production needs the row inserted
by a migration — same pattern as migrations 024 and 042.)

The LM150 is the FlyingVoice / Vola Cloud-managed VoLTE device used for the
Integrity Property Management — Belle Terre at Sunrise elevator deployment.
It is a separate product line from the FlyingVoice PR12 that the Vola sync
creates automatically.

Each row is inserted only when absent, so this migration is safe to
re-run and will not disturb a catalog row already present.
"""

import sqlalchemy as sa
from alembic import op

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None

# (id, manufacturer, model_name, device_type)
HARDWARE_MODELS = [
    ("flyingvoice-lm150", "FlyingVoice", "FlyingVoice LM150", "VoLTE ATA"),
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
