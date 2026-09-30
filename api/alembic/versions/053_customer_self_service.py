"""Customer Self-Service — customer-owned layer, governed requests, activity.

Revision ID: 053
Revises: 052
Create Date: 2026-09-30

Additive only.  Creates three NEW tables for the customer operations console:

  * ``customer_service_requests`` — governed customer requests (add / remove /
    move service, change number, replace equipment, E911 verification, location
    correction, problem report).  Operations review every one; nothing here
    changes carrier / device / network / registry / official-E911 data.
  * ``customer_managed_fields``   — the customer-owned overlay (contacts, notes,
    friendly names, connection purpose, notification preferences).
  * ``customer_activity_events``  — append-only customer-plane history (who /
    what / when / old / new / origin).

The whole surface self-gates on FEATURE_CUSTOMER_SELF_SERVICE (default off), so
this is a no-op deploy until the flag is turned on for a tenant.  Chains off the
single current head ``052`` (the 050/051 fork was resolved in PR #180; there is
no ``050`` file).  Existence-guarded for idempotency; plain portable column types
(no JSONB) so the tables also build on the SQLite test engine.  The downgrade
drops only these three tables.
"""

import sqlalchemy as sa
from alembic import op

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "customer_service_requests" not in existing:
        op.create_table(
            "customer_service_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("request_ref", sa.String(40), nullable=False),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("location_key", sa.String(80), nullable=False),
            sa.Column("building_id", sa.Integer(), nullable=True),
            sa.Column("site_id", sa.String(50), nullable=True),
            sa.Column("connection_key", sa.String(120), nullable=True),
            sa.Column("request_type", sa.String(40), nullable=False),
            sa.Column("status", sa.String(30), nullable=False, server_default="submitted"),
            sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),
            sa.Column("requested_by", sa.String(255), nullable=False),
            sa.Column("requested_by_name", sa.String(255), nullable=True),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("customer_notes", sa.Text(), nullable=True),
            sa.Column("requested_changes", sa.Text(), nullable=True),
            sa.Column("reviewed_by", sa.String(255), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolution_notes", sa.Text(), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_customer_service_requests_request_ref", "customer_service_requests",
                        ["request_ref"], unique=True)
        op.create_index("ix_customer_service_requests_tenant_id", "customer_service_requests",
                        ["tenant_id"])
        op.create_index("ix_customer_service_requests_location_key", "customer_service_requests",
                        ["location_key"])
        op.create_index("ix_customer_service_requests_status", "customer_service_requests",
                        ["status"])
        op.create_index("ix_customer_requests_tenant_status", "customer_service_requests",
                        ["tenant_id", "status"])
        op.create_index("ix_customer_requests_tenant_location", "customer_service_requests",
                        ["tenant_id", "location_key"])

    if "customer_managed_fields" not in existing:
        op.create_table(
            "customer_managed_fields",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("location_key", sa.String(80), nullable=False),
            sa.Column("building_id", sa.Integer(), nullable=True),
            sa.Column("site_id", sa.String(50), nullable=True),
            sa.Column("subject_key", sa.String(120), nullable=False, server_default=""),
            sa.Column("field", sa.String(60), nullable=False),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("updated_by", sa.String(255), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "location_key", "subject_key", "field",
                                name="uq_customer_managed_field"),
        )
        op.create_index("ix_customer_managed_fields_tenant_id", "customer_managed_fields",
                        ["tenant_id"])
        op.create_index("ix_customer_fields_tenant_location", "customer_managed_fields",
                        ["tenant_id", "location_key"])

    if "customer_activity_events" not in existing:
        op.create_table(
            "customer_activity_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("location_key", sa.String(80), nullable=True),
            sa.Column("building_id", sa.Integer(), nullable=True),
            sa.Column("site_id", sa.String(50), nullable=True),
            sa.Column("subject_key", sa.String(120), nullable=True),
            sa.Column("request_ref", sa.String(40), nullable=True),
            sa.Column("event_type", sa.String(50), nullable=False),
            sa.Column("field", sa.String(60), nullable=True),
            sa.Column("old_value", sa.Text(), nullable=True),
            sa.Column("new_value", sa.Text(), nullable=True),
            sa.Column("summary", sa.String(255), nullable=False),
            sa.Column("origin", sa.String(30), nullable=False),
            sa.Column("actor_email", sa.String(255), nullable=False),
            sa.Column("actor_name", sa.String(255), nullable=True),
            sa.Column("actor_role", sa.String(50), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_customer_activity_events_tenant_id", "customer_activity_events",
                        ["tenant_id"])
        op.create_index("ix_customer_activity_events_request_ref", "customer_activity_events",
                        ["request_ref"])
        op.create_index("ix_customer_activity_tenant_location", "customer_activity_events",
                        ["tenant_id", "location_key"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for table in ("customer_activity_events", "customer_managed_fields",
                  "customer_service_requests"):
        if table in existing:
            op.drop_table(table)
