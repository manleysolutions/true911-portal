"""Portfolio Registry — persistent Digital-Twin building registry.

Revision ID: 051
Revises: 049
Create Date: 2026-07-02

Additive only.  Creates the four Portfolio Registry tables that make the customer
portfolio persistent, so the Fusion Engine reconciles incoming data against an
approved registry instead of rediscovering the portfolio every run:

  * ``portfolio_buildings``        — canonical buildings (the Digital-Twin spine).
  * ``portfolio_aliases``          — approved label→building aliases.
  * ``portfolio_device_mappings``  — approved identifier→building mappings.
  * ``portfolio_review_items``     — the review queue (nothing enters the registry
                                     without clearing a review item).

All four are guarded by table-existence checks (idempotent, safe to re-run) and
touch no existing table.  The downgrade is a clean drop of only these tables.

NOTE: chains off 049 (the committed head); the ops-center resolution-intelligence
migration is a separate, not-yet-merged work-in-progress.
"""

import sqlalchemy as sa
from alembic import op

revision = "051"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "portfolio_buildings" not in existing:
        op.create_table(
            "portfolio_buildings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("canonical_name", sa.String(255), nullable=False),
            sa.Column("store_number", sa.String(30), nullable=True),
            sa.Column("site_type", sa.String(50), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="active"),
            sa.Column("address", sa.String(255), nullable=True),
            sa.Column("city", sa.String(120), nullable=True),
            sa.Column("state", sa.String(50), nullable=True),
            sa.Column("zip", sa.String(30), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("approved_by", sa.String(255), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_portfolio_buildings_tenant_id", "portfolio_buildings", ["tenant_id"])
        op.create_index("ix_portfolio_buildings_store_number", "portfolio_buildings", ["store_number"])
        op.create_index("ix_portfolio_buildings_tenant_store", "portfolio_buildings",
                        ["tenant_id", "store_number"])

    if "portfolio_aliases" not in existing:
        op.create_table(
            "portfolio_aliases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("building_id", sa.Integer(), nullable=False),
            sa.Column("alias", sa.String(255), nullable=False),
            sa.Column("alias_normalized", sa.String(255), nullable=False),
            sa.Column("source", sa.String(30), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="100"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "alias_normalized", name="uq_portfolio_alias_norm"),
        )
        op.create_index("ix_portfolio_aliases_tenant_id", "portfolio_aliases", ["tenant_id"])
        op.create_index("ix_portfolio_aliases_building_id", "portfolio_aliases", ["building_id"])
        op.create_index("ix_portfolio_aliases_alias_normalized", "portfolio_aliases",
                        ["alias_normalized"])

    if "portfolio_device_mappings" not in existing:
        op.create_table(
            "portfolio_device_mappings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("building_id", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(30), nullable=False),
            sa.Column("value", sa.String(255), nullable=False),
            sa.Column("value_normalized", sa.String(255), nullable=False),
            sa.Column("source", sa.String(30), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="100"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "kind", "value_normalized", name="uq_portfolio_devmap"),
        )
        op.create_index("ix_portfolio_device_mappings_tenant_id", "portfolio_device_mappings",
                        ["tenant_id"])
        op.create_index("ix_portfolio_device_mappings_building_id", "portfolio_device_mappings",
                        ["building_id"])
        op.create_index("ix_portfolio_device_mappings_value_normalized", "portfolio_device_mappings",
                        ["value_normalized"])

    if "portfolio_review_items" not in existing:
        op.create_table(
            "portfolio_review_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("review_type", sa.String(40), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("signature", sa.String(255), nullable=False),
            sa.Column("candidate_name", sa.String(255), nullable=True),
            sa.Column("store_number", sa.String(30), nullable=True),
            sa.Column("suggested_building_id", sa.Integer(), nullable=True),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("payload", sa.Text(), nullable=True),
            sa.Column("decided_by", sa.String(255), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "signature", name="uq_portfolio_review_sig"),
        )
        op.create_index("ix_portfolio_review_items_tenant_id", "portfolio_review_items", ["tenant_id"])
        op.create_index("ix_portfolio_review_items_status", "portfolio_review_items", ["status"])
        op.create_index("ix_portfolio_review_tenant_status", "portfolio_review_items",
                        ["tenant_id", "status"])


def downgrade() -> None:
    for tbl in ("portfolio_review_items", "portfolio_device_mappings",
                "portfolio_aliases", "portfolio_buildings"):
        op.drop_table(tbl)
