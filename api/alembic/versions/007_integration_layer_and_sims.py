"""Add integration layer tables: integrations, integration_accounts, integration_status,
integration_payloads, sims, device_sims, sim_events, sim_usage_daily, jobs

Revision ID: 007
Revises: 006
Create Date: 2026-02-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- integrations ---
    op.create_table(
        "integrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("docs_url", sa.String(500), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- integration_accounts ---
    op.create_table(
        "integration_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("integration_id", sa.Integer(), sa.ForeignKey("integrations.id"), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("api_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("config", postgresql.JSONB(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "integration_id", name="uq_integration_account_tenant"),
    )

    # --- integration_status ---
    op.create_table(
        "integration_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("integration_id", sa.Integer(), sa.ForeignKey("integrations.id"), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=False, index=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.String(1000), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("integration_id", "resource_type", "resource_id", name="uq_integration_status_resource"),
    )

    # --- integration_payloads ---
    op.create_table(
        "integration_payloads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payload_id", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("source", sa.String(50), nullable=False, index=True),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("headers", postgresql.JSONB(), nullable=True),
        sa.Column("body", postgresql.JSONB(), nullable=True),
        sa.Column("raw_body", sa.Text(), nullable=True),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- jobs (must come before sim_events which references it) ---
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_type", sa.String(100), nullable=False, index=True),
        sa.Column("queue", sa.String(50), nullable=False, server_default=sa.text("'default'")),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("tenant_id", sa.String(100), nullable=True, index=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial unique index: only one non-completed job per idempotency key
    op.create_index(
        "uq_jobs_idempotency",
        "jobs",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('completed', 'failed')"),
    )

    # --- sims ---
    op.create_table(
        "sims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("iccid", sa.String(30), nullable=False),
        sa.Column("msisdn", sa.String(20), nullable=True),
        sa.Column("imsi", sa.String(20), nullable=True),
        sa.Column("carrier", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'inventory'")),
        sa.Column("plan", sa.String(100), nullable=True),
        sa.Column("apn", sa.String(100), nullable=True),
        sa.Column("provider_sim_id", sa.String(255), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("uq_sims_iccid", "sims", ["iccid"], unique=True)
    op.create_index(
        "uq_sims_msisdn", "sims", ["msisdn"], unique=True,
        postgresql_where=sa.text("msisdn IS NOT NULL"),
    )
    op.create_index(
        "uq_sims_imsi", "sims", ["imsi"], unique=True,
        postgresql_where=sa.text("imsi IS NOT NULL"),
    )

    # --- device_sims ---
    op.create_table(
        "device_sims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id"), nullable=False, index=True),
        sa.Column("sim_id", sa.Integer(), sa.ForeignKey("sims.id"), nullable=False, index=True),
        sa.Column("slot", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("assigned_by", sa.String(255), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
    )
    # One active assignment per SIM at a time
    op.create_index(
        "uq_device_sims_active_sim", "device_sims", ["sim_id"],
        unique=True, postgresql_where=sa.text("active = true"),
    )
    # One active SIM per device slot at a time
    op.create_index(
        "uq_device_sims_active_slot", "device_sims", ["device_id", "slot"],
        unique=True, postgresql_where=sa.text("active = true"),
    )

    # --- sim_events ---
    op.create_table(
        "sim_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sim_id", sa.Integer(), sa.ForeignKey("sims.id"), nullable=False, index=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("status_before", sa.String(30), nullable=True),
        sa.Column("status_after", sa.String(30), nullable=True),
        sa.Column("initiated_by", sa.String(255), nullable=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- sim_usage_daily ---
    op.create_table(
        "sim_usage_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sim_id", sa.Integer(), sa.ForeignKey("sims.id"), nullable=False, index=True),
        sa.Column("usage_date", sa.Date(), nullable=False, index=True),
        sa.Column("bytes_up", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("bytes_down", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("sms_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("sim_id", "usage_date", name="uq_sim_usage_daily_date"),
    )


def downgrade() -> None:
    op.drop_table("sim_usage_daily")
    op.drop_table("sim_events")
    op.drop_index("uq_device_sims_active_slot", table_name="device_sims")
    op.drop_index("uq_device_sims_active_sim", table_name="device_sims")
    op.drop_table("device_sims")
    op.drop_index("uq_sims_imsi", table_name="sims")
    op.drop_index("uq_sims_msisdn", table_name="sims")
    op.drop_index("uq_sims_iccid", table_name="sims")
    op.drop_table("sims")
    op.drop_index("uq_jobs_idempotency", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("integration_payloads")
    op.drop_table("integration_status")
    op.drop_table("integration_accounts")
    op.drop_table("integrations")
