"""Add integration_events, customers, subscriptions, external maps, reconciliation_snapshots,
and subscription_id column on lines.

Revision ID: 008
Revises: 007
Create Date: 2026-03-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- integration_events ---
    op.create_table(
        "integration_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.String(100), nullable=False, index=True),
        sa.Column("source", sa.String(50), nullable=False, index=True),
        sa.Column("event_type", sa.String(100), nullable=False, index=True),
        sa.Column("external_id", sa.String(255), nullable=True, index=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False, index=True),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'received'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source", "idempotency_key", name="uq_integration_events_idempotency"),
    )

    # --- customers ---
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("billing_email", sa.String(255), nullable=True),
        sa.Column("billing_phone", sa.String(50), nullable=True),
        sa.Column("billing_address", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- subscriptions ---
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("plan_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'active'")),
        sa.Column("mrr", sa.Numeric(10, 2), nullable=True),
        sa.Column("qty_lines", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("renewal_date", sa.Date(), nullable=True),
        sa.Column("external_subscription_id", sa.String(255), nullable=True, index=True),
        sa.Column("external_source", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- external_customer_map ---
    op.create_table(
        "external_customer_map",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.String(100), nullable=False, index=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_account_id", sa.String(255), nullable=False),
        sa.Column("true911_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "source", "external_account_id", name="uq_ext_customer_map"),
    )

    # --- external_subscription_map ---
    op.create_table(
        "external_subscription_map",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.String(100), nullable=False, index=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_subscription_id", sa.String(255), nullable=False),
        sa.Column("true911_subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "source", "external_subscription_id", name="uq_ext_subscription_map"),
    )

    # --- reconciliation_snapshots ---
    op.create_table(
        "reconciliation_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.String(100), nullable=False, index=True),
        sa.Column("total_customers", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_subscriptions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_billed_lines", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_deployed_lines", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("mismatches_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("results_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- extend lines with subscription_id ---
    op.add_column("lines", sa.Column("subscription_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_lines_subscription_id", "lines", "subscriptions", ["subscription_id"], ["id"])
    op.add_column("lines", sa.Column("customer_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_lines_customer_id", "lines", "customers", ["customer_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_lines_customer_id", "lines", type_="foreignkey")
    op.drop_column("lines", "customer_id")
    op.drop_constraint("fk_lines_subscription_id", "lines", type_="foreignkey")
    op.drop_column("lines", "subscription_id")
    op.drop_table("reconciliation_snapshots")
    op.drop_table("external_subscription_map")
    op.drop_table("external_customer_map")
    op.drop_table("subscriptions")
    op.drop_table("customers")
    op.drop_table("integration_events")
