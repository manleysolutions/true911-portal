"""Add additive lifecycle_status columns to sites — Phase 5 (Zoho promotion target).

Revision ID: 048
Revises: 047
Create Date: 2026-06-02

Additive only.  Adds three NULLABLE columns to ``sites`` so a CONFIRMED-mapped
Zoho lifecycle_state can be promoted onto the site WITHOUT touching the
operational ``sites.status`` column (a separate axis owned by True911 telemetry)
and without deleting anything:

  * ``lifecycle_status``     — Active / Suspended / Deactivated / Pending Install / Unknown
  * ``lifecycle_source``     — e.g. "zoho_crm"
  * ``lifecycle_synced_at``  — when the lifecycle was last promoted

All three default to NULL, so existing rows are unaffected (NULL = not governed
by Zoho).  Each column is added only when absent, so the migration is idempotent
and safe to re-run.  The downgrade drops only these three new columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None

_NEW_COLUMNS = (
    ("lifecycle_status", sa.String(30)),
    ("lifecycle_source", sa.String(50)),
    ("lifecycle_synced_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("sites")}
    for name, coltype in _NEW_COLUMNS:
        if name not in existing:
            op.add_column("sites", sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("sites")}
    for name, _ in reversed(_NEW_COLUMNS):
        if name in existing:
            op.drop_column("sites", name)
