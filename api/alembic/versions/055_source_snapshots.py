"""Operational source snapshots - immutable evidence (D-024).

Revision ID: 055
Revises: 054
Create Date: 2026-09-30

Additive only.  Creates two NEW tables, ``source_snapshots`` and
``source_snapshot_records``, written only by ``scripts.source_snapshot_import
--apply``.  NOT existence-guarded: if either table already exists the upgrade
fails loudly rather than adopting an unknown schema.  Portable column types so
the tables also build on the SQLite test engine.  Downgrade drops exactly these
two tables.  Chains off the single head ``054``.
"""

import sqlalchemy as sa
from alembic import op

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None

# The tables this revision creates and owns (creation order).
OWNED_TABLES = ("source_snapshots", "source_snapshot_records")

_TS = dict(timezone=True)


def upgrade() -> None:
    bind = op.get_bind()
    preexisting = sorted(set(sa.inspect(bind).get_table_names()) & set(OWNED_TABLES))
    if preexisting:
        raise RuntimeError(
            "migration 055 refuses to run: source snapshot table(s) already exist: %s. "
            "Revision 055 must create them; investigate and remove the unexpected "
            "table(s) before upgrading." % ", ".join(preexisting))

    op.create_table(
        "source_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("source_system", sa.String(20), nullable=False),
        sa.Column("source_label", sa.String(120), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("original_basename", sa.String(255), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("parser_name", sa.String(60), nullable=False),
        sa.Column("parser_version", sa.String(40), nullable=False),
        sa.Column("status_map_version", sa.String(60), nullable=False),
        sa.Column("attribution_rule_version", sa.String(60), nullable=False),
        sa.Column("source_effective_at", sa.DateTime(**_TS), nullable=True),
        sa.Column("effective_at_basis", sa.String(20), nullable=False),
        sa.Column("imported_at", sa.DateTime(**_TS), nullable=False),
        sa.Column("imported_by", sa.String(255), nullable=False),
        sa.Column("row_count_total", sa.Integer(), nullable=False),
        sa.Column("row_count_attributed", sa.Integer(), nullable=False),
        sa.Column("row_count_excluded", sa.Integer(), nullable=False),
        sa.Column("row_count_ambiguous", sa.Integer(), nullable=False),
        sa.Column("row_count_invalid", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(**_TS), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "source_system", "file_sha256",
                            name="uq_source_snapshot_sha"),
    )
    op.create_index("ix_source_snapshots_tenant_id", "source_snapshots", ["tenant_id"])
    op.create_index("ix_source_snapshots_tenant_source", "source_snapshots",
                    ["tenant_id", "source_system"])

    op.create_table(
        "source_snapshot_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("source_system", sa.String(20), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_record_key", sa.String(120), nullable=False),
        sa.Column("identifier_type", sa.String(20), nullable=False),
        sa.Column("normalized_identifier", sa.String(120), nullable=False),
        sa.Column("msisdn", sa.String(20), nullable=True),
        sa.Column("iccid", sa.String(40), nullable=True),
        sa.Column("imei", sa.String(40), nullable=True),
        sa.Column("napco_radio", sa.String(40), nullable=True),
        sa.Column("source_status_raw", sa.String(120), nullable=True),
        sa.Column("lifecycle_interpretation", sa.String(20), nullable=False),
        sa.Column("interpretation_rule", sa.String(120), nullable=False),
        sa.Column("activity_at", sa.DateTime(**_TS), nullable=True),
        sa.Column("location_hint", sa.String(255), nullable=True),
        sa.Column("attribution_basis", sa.String(60), nullable=False),
        sa.Column("attribution_confidence", sa.String(10), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("attributes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(**_TS), server_default=sa.func.now()),
        sa.UniqueConstraint("snapshot_id", "row_number", name="uq_snapshot_record_row"),
    )
    op.create_index("ix_source_snapshot_records_snapshot_id", "source_snapshot_records",
                    ["snapshot_id"])
    op.create_index("ix_source_snapshot_records_tenant_id", "source_snapshot_records",
                    ["tenant_id"])
    op.create_index("ix_snapshot_records_identifier", "source_snapshot_records",
                    ["tenant_id", "source_system", "normalized_identifier"])


def downgrade() -> None:
    # drops exactly the two tables revision 055 created (reverse order)
    for table in reversed(OWNED_TABLES):
        op.drop_table(table)
