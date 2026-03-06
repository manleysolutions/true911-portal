"""019 – Address enrichment columns on sites

Adds columns to track address provenance and E911 confirmation status:
  - address_source: where the final address came from
  - e911_status: confirmed | temporary | needs_review | unverified
  - e911_confirmation_required: boolean flag for operational queues
  - address_notes: free-text notes about address resolution
"""

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("address_source", sa.String(50), nullable=True))
    op.add_column("sites", sa.Column("e911_status", sa.String(30), nullable=True))
    op.add_column(
        "sites",
        sa.Column(
            "e911_confirmation_required",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column("sites", sa.Column("address_notes", sa.Text(), nullable=True))

    # Index for operational queries: "show me all sites needing E911 confirmation"
    op.create_index(
        "ix_sites_e911_confirmation_required",
        "sites",
        ["e911_confirmation_required"],
        postgresql_where=sa.text("e911_confirmation_required = true"),
    )
    op.create_index("ix_sites_e911_status", "sites", ["e911_status"])


def downgrade() -> None:
    op.drop_index("ix_sites_e911_status", table_name="sites")
    op.drop_index("ix_sites_e911_confirmation_required", table_name="sites")
    op.drop_column("sites", "address_notes")
    op.drop_column("sites", "e911_confirmation_required")
    op.drop_column("sites", "e911_status")
    op.drop_column("sites", "address_source")
