"""Phase A — onboarding review queue table.

Revision ID: 041
Revises: 040
Create Date: 2026-05-12

Additive only.  Creates one new table — ``onboarding_reviews`` — that
backs the Data Steward triage queue.  Has no foreign keys to production
rows (entity_id / external_ref are free-form strings), so a downgrade
is a clean ``drop_table`` with no cascade risk.
"""

from alembic import op
import sqlalchemy as sa


revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("review_id", sa.String(50), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=True),
        sa.Column("external_ref", sa.String(255), nullable=True),
        sa.Column("issue_type", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="pending_review",
        ),
        sa.Column(
            "priority",
            sa.String(10),
            nullable=False,
            server_default="normal",
        ),
        sa.Column("assigned_to", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
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
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_onboarding_reviews_review_id",
        "onboarding_reviews",
        ["review_id"],
        unique=True,
    )
    op.create_index(
        "ix_onboarding_reviews_tenant_id",
        "onboarding_reviews",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_onboarding_reviews_entity_type",
        "onboarding_reviews",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_onboarding_reviews_entity_id",
        "onboarding_reviews",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_onboarding_reviews_external_ref",
        "onboarding_reviews",
        ["external_ref"],
        unique=False,
    )
    op.create_index(
        "ix_onboarding_reviews_status",
        "onboarding_reviews",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_onboarding_reviews_issue_type",
        "onboarding_reviews",
        ["issue_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_onboarding_reviews_issue_type", table_name="onboarding_reviews")
    op.drop_index("ix_onboarding_reviews_status", table_name="onboarding_reviews")
    op.drop_index("ix_onboarding_reviews_external_ref", table_name="onboarding_reviews")
    op.drop_index("ix_onboarding_reviews_entity_id", table_name="onboarding_reviews")
    op.drop_index("ix_onboarding_reviews_entity_type", table_name="onboarding_reviews")
    op.drop_index("ix_onboarding_reviews_tenant_id", table_name="onboarding_reviews")
    op.drop_index("ix_onboarding_reviews_review_id", table_name="onboarding_reviews")
    op.drop_table("onboarding_reviews")
