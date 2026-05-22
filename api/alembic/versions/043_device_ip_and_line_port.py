"""Add device network IP columns and line FXS port index (Phase 1).

Revision ID: 043
Revises: 042
Create Date: 2026-05-22

Additive only.  Schema-only.  Rollback-safe.  No data is written,
modified, or deleted by this migration.

Adds three new nullable columns that let the platform record the
addressing and port topology of a managed POTS replacement deployment
(Red Tag Line):

  - devices.wan_ip    VARCHAR(45)  NULL  — public / static WAN IP of a
                                          cellular modem / router
  - devices.lan_ip    VARCHAR(45)  NULL  — local LAN IP of an on-site
                                          device (e.g. a Cisco ATA)
  - lines.port_index  INTEGER      NULL  — analog FXS port a voice line
                                          terminates on (e.g. 1 or 2 on
                                          a 2-port ATA)

Adding a nullable column with no default is a metadata-only change in
modern PostgreSQL — no table rewrite, no lock contention.  Every
existing row is left untouched (the new columns are NULL).  Each
``add_column`` is guarded by an inspector check so the migration is
idempotent and safe to re-run on a populated production database.

Does NOT: backfill data, touch existing rows, add constraints / FKs /
indexes, or change any existing column.
"""

import sqlalchemy as sa
from alembic import op

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    """Return the set of existing column names for ``table``."""
    bind = op.get_bind()
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    device_cols = _columns("devices")
    if "wan_ip" not in device_cols:
        op.add_column("devices", sa.Column("wan_ip", sa.String(45), nullable=True))
    if "lan_ip" not in device_cols:
        op.add_column("devices", sa.Column("lan_ip", sa.String(45), nullable=True))

    line_cols = _columns("lines")
    if "port_index" not in line_cols:
        op.add_column("lines", sa.Column("port_index", sa.Integer(), nullable=True))


def downgrade() -> None:
    line_cols = _columns("lines")
    if "port_index" in line_cols:
        op.drop_column("lines", "port_index")

    device_cols = _columns("devices")
    if "lan_ip" in device_cols:
        op.drop_column("devices", "lan_ip")
    if "wan_ip" in device_cols:
        op.drop_column("devices", "wan_ip")
