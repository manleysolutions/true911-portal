"""Phase R1 — registration staging tables.

Revision ID: 040
Revises: 039
Create Date: 2026-05-10

Additive only.  Creates four new tables that stage a self-service
customer onboarding submission before any production rows (customers,
sites, service_units, users, devices, ...) are created.

Tables:
  - registrations                  — top-level intake record
  - registration_locations         — per-location address + access info
  - registration_service_units     — per-endpoint requested service units
  - registration_status_events     — append-only lifecycle audit trail

The conversion path that materialises customers / sites / service units
from these rows is intentionally NOT part of this migration.  Phase R1
ships the schema and the public intake API only.

Foreign keys to production tables (customers, sites, service_units,
users) are nullable with ON DELETE SET NULL — the registration record
survives independently of any later materialised row.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── registrations ────────────────────────────────────────────────
    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("registration_id", sa.String(50), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False, server_default="ops"),
        sa.Column("status", sa.String(40), nullable=False, server_default="draft"),

        # Resume-token (hashed, never stored plaintext).
        sa.Column("resume_token_hash", sa.String(128), nullable=False),
        sa.Column("resume_token_expires_at", sa.DateTime(timezone=True), nullable=False),

        # Step 1 — submitter / customer identity
        sa.Column("submitter_email", sa.String(255), nullable=False),
        sa.Column("submitter_name", sa.String(255), nullable=True),
        sa.Column("submitter_phone", sa.String(50), nullable=True),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("customer_legal_name", sa.String(255), nullable=True),
        sa.Column("customer_account_number", sa.String(100), nullable=True),

        # Step 1 / 8 — primary point of contact
        sa.Column("poc_name", sa.String(255), nullable=True),
        sa.Column("poc_phone", sa.String(50), nullable=True),
        sa.Column("poc_email", sa.String(255), nullable=True),
        sa.Column("poc_role", sa.String(100), nullable=True),

        # Step 3 — use case (free text)
        sa.Column("use_case_summary", sa.Text(), nullable=True),

        # Step 4 — plan selection (text-only per R1 decision)
        sa.Column("selected_plan_code", sa.String(100), nullable=True),
        sa.Column("plan_quantity_estimate", sa.Integer(), nullable=True),

        # Step 7 — billing intake
        sa.Column("billing_email", sa.String(255), nullable=True),
        sa.Column("billing_address_street", sa.String(500), nullable=True),
        sa.Column("billing_address_city", sa.String(100), nullable=True),
        sa.Column("billing_address_state", sa.String(50), nullable=True),
        sa.Column("billing_address_zip", sa.String(30), nullable=True),
        sa.Column("billing_address_country", sa.String(50), nullable=True),
        sa.Column("billing_method", sa.String(50), nullable=True),

        # Step 8 — support preferences (channel, after-hours contacts, etc.)
        sa.Column("support_preference_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        # Step 6 — install scheduling (manual capture; no Field Nation calls)
        sa.Column("preferred_install_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preferred_install_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("installer_notes", sa.Text(), nullable=True),

        # Step 9 — internal review fields (no assignment logic in R1)
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),

        # Conversion linkage — set at later phases; nullable forever.
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("target_tenant_id", sa.String(100), nullable=True),

        # Lifecycle timestamps
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),

        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_registrations_registration_id", "registrations", ["registration_id"]
    )
    op.create_index("ix_registrations_registration_id", "registrations", ["registration_id"])
    op.create_index("ix_registrations_tenant_id", "registrations", ["tenant_id"])
    op.create_index("ix_registrations_status", "registrations", ["status"])
    op.create_index("ix_registrations_submitter_email", "registrations", ["submitter_email"])
    op.create_index("ix_registrations_customer_id", "registrations", ["customer_id"])

    # FK to customers — nullable, SET NULL on customer delete so a
    # surviving registration record retains its history if the customer
    # row is removed.  NOT VALID matches the Phase 3a customer_id pattern.
    op.create_foreign_key(
        "fk_registrations_customer_id",
        source_table="registrations",
        referent_table="customers",
        local_cols=["customer_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
        onupdate="CASCADE",
        postgresql_not_valid=True,
    )

    # FK to users for reviewer_user_id — nullable, SET NULL on user delete.
    op.create_foreign_key(
        "fk_registrations_reviewer_user_id",
        source_table="registrations",
        referent_table="users",
        local_cols=["reviewer_user_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
        onupdate="CASCADE",
        postgresql_not_valid=True,
    )

    # ── registration_locations ──────────────────────────────────────
    op.create_table(
        "registration_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("registration_id", sa.Integer(), nullable=False),
        sa.Column("location_label", sa.String(255), nullable=False),
        sa.Column("street", sa.String(500), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(50), nullable=True),
        sa.Column("zip", sa.String(30), nullable=True),
        sa.Column("country", sa.String(50), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("poc_name", sa.String(255), nullable=True),
        sa.Column("poc_phone", sa.String(50), nullable=True),
        sa.Column("poc_email", sa.String(255), nullable=True),
        sa.Column("dispatchable_description", sa.Text(), nullable=True),
        sa.Column("access_notes", sa.Text(), nullable=True),
        sa.Column("materialized_site_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["registration_id"],
            ["registrations.id"],
            name="fk_reg_locations_registration_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_reg_locations_registration_id",
        "registration_locations",
        ["registration_id"],
    )
    op.create_foreign_key(
        "fk_reg_locations_materialized_site_id",
        source_table="registration_locations",
        referent_table="sites",
        local_cols=["materialized_site_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
        onupdate="CASCADE",
        postgresql_not_valid=True,
    )

    # ── registration_service_units ──────────────────────────────────
    op.create_table(
        "registration_service_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("registration_id", sa.Integer(), nullable=False),
        sa.Column("registration_location_id", sa.Integer(), nullable=False),
        sa.Column("unit_label", sa.String(255), nullable=False),
        sa.Column("unit_type", sa.String(50), nullable=False),
        sa.Column("phone_number_existing", sa.String(50), nullable=True),
        sa.Column("hardware_model_request", sa.String(255), nullable=True),
        sa.Column("carrier_request", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("install_type", sa.String(30), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("materialized_service_unit_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["registration_id"],
            ["registrations.id"],
            name="fk_reg_units_registration_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["registration_location_id"],
            ["registration_locations.id"],
            name="fk_reg_units_location_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_reg_units_registration_id",
        "registration_service_units",
        ["registration_id"],
    )
    op.create_index(
        "ix_reg_units_location_id",
        "registration_service_units",
        ["registration_location_id"],
    )
    op.create_foreign_key(
        "fk_reg_units_materialized_service_unit_id",
        source_table="registration_service_units",
        referent_table="service_units",
        local_cols=["materialized_service_unit_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
        onupdate="CASCADE",
        postgresql_not_valid=True,
    )

    # ── registration_status_events ──────────────────────────────────
    op.create_table(
        "registration_status_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("registration_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(40), nullable=True),
        sa.Column("to_status", sa.String(40), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["registration_id"],
            ["registrations.id"],
            name="fk_reg_status_events_registration_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_reg_status_events_actor_user_id",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
    )
    op.create_index(
        "ix_reg_status_events_registration_id",
        "registration_status_events",
        ["registration_id", "created_at"],
    )


def downgrade() -> None:
    # Pure inverse: drop in FK order — children before parents.
    op.drop_index("ix_reg_status_events_registration_id", table_name="registration_status_events")
    op.drop_table("registration_status_events")

    op.drop_constraint(
        "fk_reg_units_materialized_service_unit_id",
        "registration_service_units",
        type_="foreignkey",
    )
    op.drop_index("ix_reg_units_location_id", table_name="registration_service_units")
    op.drop_index("ix_reg_units_registration_id", table_name="registration_service_units")
    op.drop_table("registration_service_units")

    op.drop_constraint(
        "fk_reg_locations_materialized_site_id",
        "registration_locations",
        type_="foreignkey",
    )
    op.drop_index("ix_reg_locations_registration_id", table_name="registration_locations")
    op.drop_table("registration_locations")

    op.drop_constraint("fk_registrations_reviewer_user_id", "registrations", type_="foreignkey")
    op.drop_constraint("fk_registrations_customer_id", "registrations", type_="foreignkey")
    op.drop_index("ix_registrations_customer_id", table_name="registrations")
    op.drop_index("ix_registrations_submitter_email", table_name="registrations")
    op.drop_index("ix_registrations_status", table_name="registrations")
    op.drop_index("ix_registrations_tenant_id", table_name="registrations")
    op.drop_index("ix_registrations_registration_id", table_name="registrations")
    op.drop_constraint("uq_registrations_registration_id", "registrations", type_="unique")
    op.drop_table("registrations")
