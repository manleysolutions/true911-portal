"""Add nullable customer_id FK to sites (Phase 1).

Revision ID: 039
Revises: 038
Create Date: 2026-05-07

Phase 1 of the sites.customer_id rollout.  Schema-only.  Additive.
Rollback-safe.  No data is written, modified, or deleted by this
migration.

Adds:
  - sites.customer_id  INTEGER  NULL  (no default, no backfill)
  - FK fk_sites_customer_id → customers(id)
        ON DELETE RESTRICT  (a customer with linked sites cannot be
                             deleted accidentally)
        ON UPDATE CASCADE   (id changes propagate; customers.id is a
                             surrogate, so this is academic but safe)
        Created with NOT VALID on PostgreSQL — the column is brand new
        and every existing row is NULL, so there is nothing to scan.
        VALIDATE CONSTRAINT is deferred to Phase 5.
  - ix_sites_customer_id            (customer_id)
  - ix_sites_tenant_customer        (tenant_id, customer_id)

Does NOT:
  - backfill any data
  - touch existing rows
  - alter customer_name
  - change tenant logic
  - make customer_id required
  - validate the FK against historical data
"""

from alembic import op
import sqlalchemy as sa


revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Nullable column.  Adding a nullable column without a default is
    #    a metadata-only change in modern PostgreSQL — no table rewrite.
    op.add_column(
        "sites",
        sa.Column("customer_id", sa.Integer(), nullable=True),
    )

    # 2. FK constraint.  Created NOT VALID on PostgreSQL so the deploy
    #    avoids the historical-row scan.  The column has no non-NULL
    #    values, so this is purely defensive — but it makes the intent
    #    explicit and matches the Phase 5 VALIDATE CONSTRAINT step.
    op.create_foreign_key(
        "fk_sites_customer_id",
        source_table="sites",
        referent_table="customers",
        local_cols=["customer_id"],
        remote_cols=["id"],
        ondelete="RESTRICT",
        onupdate="CASCADE",
        postgresql_not_valid=True,
    )

    # 3. Indexes.  Single-column for direct customer lookups;
    #    composite for the (tenant_id, customer_id) pattern used by
    #    onboarding and reconciliation queries.
    op.create_index(
        "ix_sites_customer_id",
        "sites",
        ["customer_id"],
    )
    op.create_index(
        "ix_sites_tenant_customer",
        "sites",
        ["tenant_id", "customer_id"],
    )


def downgrade() -> None:
    # Pure inverse: drop indexes, FK, then column.  No data loss because
    # the column is brand new and customer_name remains the source of
    # truth throughout Phase 1.
    op.drop_index("ix_sites_tenant_customer", table_name="sites")
    op.drop_index("ix_sites_customer_id", table_name="sites")
    op.drop_constraint("fk_sites_customer_id", "sites", type_="foreignkey")
    op.drop_column("sites", "customer_id")
