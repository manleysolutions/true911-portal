"""Subscriber import pipeline — batch tracking, row audit, and model extensions.

Revision ID: 035
Revises: 034
Create Date: 2026-03-29

Adds:
  - import_batches table (tracks each import session)
  - import_rows table (per-row audit trail)
  - customer columns: customer_number, account_number
  - line columns: sim_iccid, carrier, line_type, reconciliation_status,
                  import_batch_id, source_row_id, qb_description
  - device columns: reconciliation_status, import_batch_id, source_row_id
  - site columns: reconciliation_status, import_batch_id
"""

from alembic import op
import sqlalchemy as sa


revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── import_batches ────────────────────────────────────────────
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("batch_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("file_name", sa.String(500), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("total_rows", sa.Integer, nullable=True),
        sa.Column("rows_created", sa.Integer, nullable=True),
        sa.Column("rows_updated", sa.Integer, nullable=True),
        sa.Column("rows_matched", sa.Integer, nullable=True),
        sa.Column("rows_failed", sa.Integer, nullable=True),
        sa.Column("rows_flagged", sa.Integer, nullable=True),
        sa.Column("tenants_created", sa.Integer, nullable=True),
        sa.Column("sites_created", sa.Integer, nullable=True),
        sa.Column("devices_created", sa.Integer, nullable=True),
        sa.Column("lines_created", sa.Integer, nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── import_rows ───────────────────────────────────────────────
    op.create_table(
        "import_rows",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("batch_id", sa.String(50), nullable=False, index=True),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        # pending | created | matched | updated | failed | flagged | skipped
        sa.Column("action_summary", sa.String(500), nullable=True),
        sa.Column("tenant_action", sa.String(30), nullable=True),
        sa.Column("site_action", sa.String(30), nullable=True),
        sa.Column("device_action", sa.String(30), nullable=True),
        sa.Column("line_action", sa.String(30), nullable=True),
        sa.Column("tenant_id_resolved", sa.String(100), nullable=True),
        sa.Column("site_id_resolved", sa.String(50), nullable=True),
        sa.Column("device_id_resolved", sa.String(50), nullable=True),
        sa.Column("line_id_resolved", sa.String(50), nullable=True),
        sa.Column("errors_json", sa.Text, nullable=True),
        sa.Column("warnings_json", sa.Text, nullable=True),
        sa.Column("raw_data_json", sa.Text, nullable=True),
        sa.Column("reconciliation_status", sa.String(30), nullable=True, server_default="imported_unverified"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Customer extensions ───────────────────────────────────────
    op.add_column("customers", sa.Column("customer_number", sa.String(100), nullable=True, index=True))
    op.add_column("customers", sa.Column("account_number", sa.String(100), nullable=True))

    # ── Line extensions ───────────────────────────────────────────
    op.add_column("lines", sa.Column("sim_iccid", sa.String(30), nullable=True))
    op.add_column("lines", sa.Column("carrier", sa.String(50), nullable=True))
    op.add_column("lines", sa.Column("line_type", sa.String(50), nullable=True))
    op.add_column("lines", sa.Column("reconciliation_status", sa.String(30), nullable=True, server_default="imported_unverified"))
    op.add_column("lines", sa.Column("import_batch_id", sa.String(50), nullable=True))
    op.add_column("lines", sa.Column("source_row_id", sa.Integer, nullable=True))
    op.add_column("lines", sa.Column("qb_description", sa.Text, nullable=True))

    # ── Device extensions ─────────────────────────────────────────
    op.add_column("devices", sa.Column("reconciliation_status", sa.String(30), nullable=True, server_default="imported_unverified"))
    op.add_column("devices", sa.Column("import_batch_id", sa.String(50), nullable=True))
    op.add_column("devices", sa.Column("source_row_id", sa.Integer, nullable=True))

    # ── Site extensions ───────────────────────────────────────────
    op.add_column("sites", sa.Column("reconciliation_status", sa.String(30), nullable=True, server_default="imported_unverified"))
    op.add_column("sites", sa.Column("import_batch_id", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("sites", "import_batch_id")
    op.drop_column("sites", "reconciliation_status")
    op.drop_column("devices", "source_row_id")
    op.drop_column("devices", "import_batch_id")
    op.drop_column("devices", "reconciliation_status")
    op.drop_column("lines", "qb_description")
    op.drop_column("lines", "source_row_id")
    op.drop_column("lines", "import_batch_id")
    op.drop_column("lines", "reconciliation_status")
    op.drop_column("lines", "line_type")
    op.drop_column("lines", "carrier")
    op.drop_column("lines", "sim_iccid")
    op.drop_column("customers", "account_number")
    op.drop_column("customers", "customer_number")
    op.drop_table("import_rows")
    op.drop_table("import_batches")
