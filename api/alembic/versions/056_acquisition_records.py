"""Acquisition records — durable public leads (D-031).

Revision ID: 056
Revises: 055
Create Date: 2026-10-01

Additive only.  Creates ONE new table, ``acquisition_records``, written by the
public submission endpoints.  Touches no existing table and no customer,
registry, canonical or E911 data.  NOT existence-guarded: if the table already
exists the upgrade fails loudly rather than adopting an unknown schema.  Portable
column types so it also builds on the SQLite test engine.  Downgrade drops
exactly this table.  Chains off the single head ``055``.
"""

import sqlalchemy as sa
from alembic import op

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None

OWNED_TABLES = ("acquisition_records",)
_TS = dict(timezone=True)


def upgrade() -> None:
    bind = op.get_bind()
    preexisting = sorted(set(sa.inspect(bind).get_table_names()) & set(OWNED_TABLES))
    if preexisting:
        raise RuntimeError(
            "migration 056 refuses to run: acquisition table(s) already exist: %s. "
            "Revision 056 must create them; investigate and remove the unexpected "
            "table(s) before upgrading." % ", ".join(preexisting))

    op.create_table(
        "acquisition_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("record_ref", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("company", sa.String(200), nullable=True),
        sa.Column("contact_name", sa.String(200), nullable=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("num_locations", sa.Integer(), nullable=True),
        sa.Column("service_interests", sa.Text(), nullable=True),
        sa.Column("needs", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("registration_ref", sa.String(40), nullable=True),
        sa.Column("entry_point", sa.String(40), nullable=False),
        sa.Column("landing_path", sa.String(300), nullable=True),
        sa.Column("referrer", sa.String(300), nullable=True),
        sa.Column("utm_source", sa.String(100), nullable=True),
        sa.Column("utm_medium", sa.String(100), nullable=True),
        sa.Column("utm_campaign", sa.String(150), nullable=True),
        sa.Column("utm_term", sa.String(150), nullable=True),
        sa.Column("utm_content", sa.String(150), nullable=True),
        sa.Column("initial_cta", sa.String(60), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("notification_status", sa.String(20), nullable=False),
        sa.Column("notification_attempts", sa.Integer(), nullable=False),
        sa.Column("notification_error", sa.String(300), nullable=True),
        sa.Column("notified_at", sa.DateTime(**_TS), nullable=True),
        sa.Column("created_at", sa.DateTime(**_TS), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(**_TS), server_default=sa.func.now()),
        sa.UniqueConstraint("record_ref", name="uq_acquisition_records_record_ref"),
        sa.UniqueConstraint("idempotency_key", name="uq_acquisition_records_idempotency_key"),
    )
    op.create_index("ix_acquisition_records_status", "acquisition_records", ["status"])
    op.create_index("ix_acquisition_records_email", "acquisition_records", ["email"])
    op.create_index("ix_acquisition_records_registration_ref", "acquisition_records",
                    ["registration_ref"])


def downgrade() -> None:
    op.drop_index("ix_acquisition_records_registration_ref", table_name="acquisition_records")
    op.drop_index("ix_acquisition_records_email", table_name="acquisition_records")
    op.drop_index("ix_acquisition_records_status", table_name="acquisition_records")
    op.drop_table("acquisition_records")
