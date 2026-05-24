"""Add llm_audit_log and llm_summary_cache tables — Phase 1 LLLM MVP.

Revision ID: 045
Revises: 044
Create Date: 2026-05-23

Additive only.  Creates two new tables:

  * ``llm_audit_log`` — one row per ``GET /api/llm/health-summary`` call;
    records WHO/WHEN/WHICH-tenant/WHICH-model/WHICH-sources/generated
    summary/confidence/tokens/latency/status.  Never persists the raw
    prompt or raw customer data — see ``docs/AI_OPERATIONAL_SAFETY.md``
    for the full contract.

  * ``llm_summary_cache`` — bounds cost and rate by reusing a generated
    summary while the inputs (``data_fingerprint``) haven't changed.

Both tables are guarded by table-existence checks so this migration is
idempotent and safe to re-run on a populated production database.  The
downgrade is a clean ``drop_table`` — both tables are new and nothing
references them.

Nothing in this migration touches any existing column or table.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


_AUDIT_INDEXES = (
    "ix_llm_audit_log_audit_id",
    "ix_llm_audit_log_effective_tenant_id",
    "ix_llm_audit_tenant_created",
)
_CACHE_INDEXES = (
    "ix_llm_summary_cache_tenant_id",
    "ix_llm_summary_cache_expires_at",
)


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "llm_audit_log" not in existing:
        op.create_table(
            "llm_audit_log",
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("audit_id", sa.String(50), nullable=False),
            sa.Column("user_id", sa.String(64), nullable=False),
            sa.Column("user_email", sa.String(255), nullable=True),
            sa.Column("user_role", sa.String(50), nullable=True),
            sa.Column("effective_tenant_id", sa.String(100), nullable=False),
            sa.Column("original_tenant_id", sa.String(100), nullable=False),
            sa.Column(
                "is_impersonating",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("scope", sa.String(20), nullable=False),
            sa.Column("scope_id", sa.String(100), nullable=True),
            sa.Column("model", sa.String(100), nullable=False),
            sa.Column("prompt_template_version", sa.String(50), nullable=False),
            sa.Column("sources_used", JSONB(), nullable=False),
            sa.Column("summary_text", sa.Text(), nullable=False),
            sa.Column("customer_safe_summary", sa.Text(), nullable=True),
            sa.Column("internal_summary", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("tokens_in", sa.Integer(), nullable=True),
            sa.Column("tokens_out", sa.Integer(), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("error_summary", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_llm_audit_log_audit_id", "llm_audit_log", ["audit_id"], unique=True
        )
        op.create_index(
            "ix_llm_audit_log_effective_tenant_id",
            "llm_audit_log",
            ["effective_tenant_id"],
        )
        op.create_index(
            "ix_llm_audit_tenant_created",
            "llm_audit_log",
            ["effective_tenant_id", "created_at"],
        )

    if "llm_summary_cache" not in existing:
        op.create_table(
            "llm_summary_cache",
            sa.Column("cache_key", sa.String(128), primary_key=True),
            sa.Column("tenant_id", sa.String(100), nullable=False),
            sa.Column("scope", sa.String(20), nullable=False),
            sa.Column("scope_id", sa.String(100), nullable=True),
            sa.Column("data_fingerprint", sa.String(64), nullable=False),
            sa.Column("payload", JSONB(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_llm_summary_cache_tenant_id", "llm_summary_cache", ["tenant_id"]
        )
        op.create_index(
            "ix_llm_summary_cache_expires_at", "llm_summary_cache", ["expires_at"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "llm_summary_cache" in existing:
        for ix in _CACHE_INDEXES:
            op.drop_index(ix, table_name="llm_summary_cache")
        op.drop_table("llm_summary_cache")

    if "llm_audit_log" in existing:
        for ix in _AUDIT_INDEXES:
            op.drop_index(ix, table_name="llm_audit_log")
        op.drop_table("llm_audit_log")
