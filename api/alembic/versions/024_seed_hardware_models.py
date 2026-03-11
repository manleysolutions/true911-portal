"""Seed hardware_models reference data (RTL lineup).

This is a data migration — it inserts the standard hardware catalog
so the dropdown works in production (seed.py only runs in demo mode).

Revision ID: 024
Revises: 023
"""

import sqlalchemy as sa
from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None

HARDWARE_MODELS = [
    ("etross-ms130v4",   "ETROSS",        "MS130v4 (ETROSS 8848)",      "Cellular Modem"),
    ("atel-ms130v5",     "ATEL",          "MS130v5 (ATEL V810V)",       "Cellular Modem"),
    ("flyingvoice-pr12", "Flying Voice",  "PR12 (Flying Voice / Vola)", "Cellular Router"),
    ("inseego-fw3100",   "Inseego",       "Inseego FW3100",             "Cellular Router"),
    ("napco-slelte",     "Napco",         "SLELTE",                     "StarLink Communicator"),
    ("napco-sle5g",      "Napco",         "SLE5G",                      "StarLink Communicator"),
    ("cisco-ata191",     "Cisco",         "ATA191",                     "ATA"),
    ("cisco-ata192",     "Cisco",         "ATA192",                     "ATA"),
    ("rtl-csa-v1",       "Red Tag Lines", "CSA v1",                     "CSA"),
    ("rtl-csa-v1-4p",    "Red Tag Lines", "CSA v1 4-Port",              "CSA"),
    ("other",            "Other",         "Other",                      "Other"),
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
    # Use INSERT ... ON CONFLICT DO NOTHING so it's safe to re-run
    # if demo seed already populated the table.
    conn = op.get_bind()
    for mid, mfr, name, dtype in HARDWARE_MODELS:
        # Check if already exists (portable across dialects)
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
