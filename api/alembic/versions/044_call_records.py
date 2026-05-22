"""Add call_records (CDR) table — Phase 2.

Revision ID: 044
Revises: 043
Create Date: 2026-05-22

Additive only.  Creates one new table — ``call_records`` — that stores
call detail records (CDRs) for managed POTS replacement deployments
(Red Tag Line).  The table is empty on creation; provider ingestion
(Telnyx) lands in Phase 3.

``customer_id`` is a real FK to ``customers.id`` (nullable) so a CDR can
be FK-joined to a customer; ``tenant_id`` / ``site_id`` / ``device_id`` /
``line_id`` are indexed string business keys, matching the ``recordings``
and ``events`` tables.

The whole migration is guarded by a table-existence check, so it is
idempotent and safe to re-run on a populated production database.  A
downgrade is a clean ``drop_table`` — the table is new and nothing
references it.
"""

import sqlalchemy as sa
from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None

_INDEXES = (
    "ix_call_records_call_id",
    "ix_call_records_tenant_id",
    "ix_call_records_customer_id",
    "ix_call_records_site_id",
    "ix_call_records_device_id",
    "ix_call_records_line_id",
    "ix_call_records_started_at",
    "ix_call_records_telnyx_call_id",
    "ix_call_records_tenant_started",
)


def upgrade() -> None:
    bind = op.get_bind()
    if "call_records" in sa.inspect(bind).get_table_names():
        return

    op.create_table(
        "call_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("site_id", sa.String(50), nullable=True),
        sa.Column("device_id", sa.String(50), nullable=True),
        sa.Column("line_id", sa.String(50), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False, server_default="telnyx"),
        sa.Column("direction", sa.String(20), nullable=False, server_default="inbound"),
        sa.Column("from_number", sa.String(30), nullable=True),
        sa.Column("to_number", sa.String(30), nullable=True),
        sa.Column("did", sa.String(30), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="completed"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("recording_id", sa.String(50), nullable=True),
        sa.Column("telnyx_call_id", sa.String(128), nullable=True),
        sa.Column("telnyx_cdr_id", sa.String(128), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name="fk_call_records_customer_id"
        ),
    )

    op.create_index("ix_call_records_call_id", "call_records", ["call_id"], unique=True)
    op.create_index("ix_call_records_tenant_id", "call_records", ["tenant_id"])
    op.create_index("ix_call_records_customer_id", "call_records", ["customer_id"])
    op.create_index("ix_call_records_site_id", "call_records", ["site_id"])
    op.create_index("ix_call_records_device_id", "call_records", ["device_id"])
    op.create_index("ix_call_records_line_id", "call_records", ["line_id"])
    op.create_index("ix_call_records_started_at", "call_records", ["started_at"])
    op.create_index("ix_call_records_telnyx_call_id", "call_records", ["telnyx_call_id"])
    op.create_index(
        "ix_call_records_tenant_started", "call_records", ["tenant_id", "started_at"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "call_records" not in sa.inspect(bind).get_table_names():
        return
    for ix in _INDEXES:
        op.drop_index(ix, table_name="call_records")
    op.drop_table("call_records")
