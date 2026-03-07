"""Repair imported device records: copy sim_id → iccid where iccid is empty.

Previous importer stored SIM ICCID values in sim_id instead of iccid,
and may have missed msisdn. This migration copies data to the correct columns.

Revision ID: 022
Revises: 021
"""

from alembic import op

revision = "022"
down_revision = "021"


def upgrade() -> None:
    # Where iccid is empty but sim_id has data, copy sim_id → iccid
    op.execute("""
        UPDATE devices
        SET iccid = sim_id
        WHERE (iccid IS NULL OR iccid = '')
          AND sim_id IS NOT NULL
          AND sim_id != ''
    """)


def downgrade() -> None:
    # No safe way to reverse — data was just copied, not moved
    pass
