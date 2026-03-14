"""Add Zoho CRM linkage fields to customers and tenants.

Revision ID: 031
Revises: 030
"""

from alembic import op
import sqlalchemy as sa

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Customer: Zoho CRM linkage
    op.add_column("customers", sa.Column("zoho_account_id", sa.String(50), nullable=True, index=True))
    op.add_column("customers", sa.Column("zoho_contact_id", sa.String(50), nullable=True))
    op.add_column("customers", sa.Column("zoho_deal_id", sa.String(50), nullable=True))
    op.add_column("customers", sa.Column("zoho_sync_status", sa.String(30), nullable=True))
    op.add_column("customers", sa.Column("zoho_last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("customers", sa.Column("onboarding_status", sa.String(30), nullable=True, server_default="pending"))

    # Tenant: Zoho linkage
    op.add_column("tenants", sa.Column("zoho_account_id", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "zoho_account_id")
    op.drop_column("customers", "onboarding_status")
    op.drop_column("customers", "zoho_last_synced_at")
    op.drop_column("customers", "zoho_sync_status")
    op.drop_column("customers", "zoho_deal_id")
    op.drop_column("customers", "zoho_contact_id")
    op.drop_column("customers", "zoho_account_id")
