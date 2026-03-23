Now I have a thorough understanding of every relevant file, pattern, and convention in this codebase. Let me compile the comprehensive implementation plan.

---

# Provider Integration Layer -- Implementation Plan

## 1. Complete File List with Changes

Below is every file that must be created or modified, organized by category. Absolute paths are relative to the project root `D:/True911_Base44_stuff/true911-prod`.

### 1.1 New Files to Create

| # | File | Purpose |
|---|------|---------|
| 1 | `api/alembic/versions/007_integration_layer_and_sims.py` | Migration: 9 new tables |
| 2 | `api/app/models/integration.py` | ORM: Integration, IntegrationAccount |
| 3 | `api/app/models/integration_status.py` | ORM: IntegrationStatus |
| 4 | `api/app/models/integration_payload.py` | ORM: IntegrationPayload |
| 5 | `api/app/models/sim.py` | ORM: Sim |
| 6 | `api/app/models/device_sim.py` | ORM: DeviceSim (join table) |
| 7 | `api/app/models/sim_event.py` | ORM: SimEvent |
| 8 | `api/app/models/sim_usage_daily.py` | ORM: SimUsageDaily |
| 9 | `api/app/models/job.py` | ORM: Job |
| 10 | `api/app/schemas/sim.py` | Pydantic: SimOut, SimCreate, SimUpdate, SimAssign |
| 11 | `api/app/schemas/job.py` | Pydantic: JobOut |
| 12 | `api/app/schemas/integration.py` | Pydantic: IntegrationOut, IntegrationAccountOut/Create/Update |
| 13 | `api/app/schemas/webhook.py` | Pydantic: WebhookPayload (generic inbound envelope) |
| 14 | `api/app/routers/sims.py` | Router: SIM CRUD + assign/unassign |
| 15 | `api/app/routers/webhooks.py` | Router: POST endpoints for Telnyx, Vola, T-Mobile |
| 16 | `api/app/routers/jobs.py` | Router: GET /jobs, GET /jobs/{id} (Admin) |
| 17 | `api/app/integrations/__init__.py` | Package init, re-exports get_client |
| 18 | `api/app/integrations/base.py` | BaseProviderClient ABC |
| 19 | `api/app/integrations/telnyx.py` | TelnyxClient |
| 20 | `api/app/integrations/vola.py` | VolaClient |
| 21 | `api/app/integrations/tmobile.py` | TMobileClient |
| 22 | `api/app/integrations/registry.py` | get_client(provider_type) factory |
| 23 | `api/app/services/sim_service.py` | SIM lifecycle service (enqueues jobs) |
| 24 | `api/app/services/line_service.py` | Line provisioning service (enqueues jobs) |
| 25 | `api/app/services/job_service.py` | Job creation + status update helpers |
| 26 | `api/worker.py` | RQ worker entry point |

### 1.2 Files to Modify

| # | File | Change |
|---|------|--------|
| 1 | `api/requirements.txt` | Add `redis==5.0.0`, `rq==1.16.0`, `httpx==0.27.0` |
| 2 | `api/app/config.py` | Add `REDIS_URL` setting |
| 3 | `api/app/models/__init__.py` | Import 8 new models, add to `__all__` |
| 4 | `api/app/main.py` | Register 3 new routers (sims, webhooks, jobs) |
| 5 | `api/app/services/rbac.py` | Add `MANAGE_SIMS`, `VIEW_JOBS`, `MANAGE_INTEGRATIONS` permissions |
| 6 | `api/app/seed.py` | Add demo SIMs, integrations, device_sims (demo mode only) |
| 7 | `render.yaml` | Add Redis service + worker service |
| 8 | `api/alembic/env.py` | No change needed (already imports `app.models`) |

---

## 2. Migration 007 Schema Design

File: `api/alembic/versions/007_integration_layer_and_sims.py`

```python
"""Add integration layer, SIM inventory, and job tracking tables

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
    # ── 1. integrations ──────────────────────────────────────────────
    # Registry of available integration types (global, not per-tenant)
    op.create_table(
        "integrations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(50), unique=True, nullable=False, index=True),
        # slug: "telnyx", "vola", "tmobile", "bandwidth", etc.
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        # category: "carrier", "sip_trunk", "hardware_mfr", "monitoring"
        sa.Column("supports_webhooks", sa.Boolean, server_default=sa.text("false")),
        sa.Column("webhook_path", sa.String(255), nullable=True),
        # e.g. "/api/webhooks/telnyx"
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── 2. integration_accounts ──────────────────────────────────────
    # Tenant-specific credentials/config for each integration
    op.create_table(
        "integration_accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("integration_slug", sa.String(50),
                  sa.ForeignKey("integrations.slug"), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("api_key_enc", sa.Text, nullable=True),
        # encrypted at rest; never returned in API responses
        sa.Column("api_secret_enc", sa.Text, nullable=True),
        sa.Column("webhook_secret_enc", sa.Text, nullable=True),
        sa.Column("config_json", postgresql.JSONB, nullable=True),
        # provider-specific config: base_url, account_sid, etc.
        sa.Column("enabled", sa.Boolean, server_default=sa.text("false")),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # One account per integration per tenant
    op.create_index(
        "uq_integration_account_tenant",
        "integration_accounts",
        ["tenant_id", "integration_slug"],
        unique=True,
    )

    # ── 3. integration_status ────────────────────────────────────────
    # Per-resource sync status tracking
    op.create_table(
        "integration_status",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("integration_slug", sa.String(50), nullable=False, index=True),
        sa.Column("resource_type", sa.String(50), nullable=False),
        # resource_type: "sim", "line", "device", "did"
        sa.Column("resource_id", sa.String(100), nullable=False),
        # our internal ID (e.g. sim_id, line_id)
        sa.Column("external_id", sa.String(255), nullable=True),
        # provider's ID for this resource
        sa.Column("sync_state", sa.String(30), nullable=False,
                  server_default="pending"),
        # pending, syncing, synced, error, stale
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "uq_integration_status_resource",
        "integration_status",
        ["integration_slug", "resource_type", "resource_id"],
        unique=True,
    )

    # ── 4. integration_payloads ──────────────────────────────────────
    # Raw webhook/API payloads for audit
    op.create_table(
        "integration_payloads",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("payload_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=True, index=True),
        # nullable: webhook may arrive before we resolve the tenant
        sa.Column("integration_slug", sa.String(50), nullable=False, index=True),
        sa.Column("direction", sa.String(10), nullable=False),
        # "inbound" (webhook) or "outbound" (our API call to provider)
        sa.Column("event_type", sa.String(100), nullable=True),
        # provider-specific event type from the webhook
        sa.Column("http_method", sa.String(10), nullable=True),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column("headers_json", postgresql.JSONB, nullable=True),
        sa.Column("body_json", postgresql.JSONB, nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("response_json", postgresql.JSONB, nullable=True),
        sa.Column("processed", sa.Boolean, server_default=sa.text("false")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── 5. sims ──────────────────────────────────────────────────────
    op.create_table(
        "sims",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sim_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("iccid", sa.String(30), nullable=False),
        # iccid is the SIM's primary physical identifier
        sa.Column("msisdn", sa.String(20), nullable=True),
        sa.Column("imsi", sa.String(20), nullable=True),
        sa.Column("provider_type", sa.String(50), nullable=False),
        # "telnyx", "tmobile", "vola", etc.
        sa.Column("plan_name", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="inventory"),
        # inventory, active, suspended, terminated
        sa.Column("activation_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_sims_iccid ON sims(iccid)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_sims_msisdn ON sims(msisdn) WHERE msisdn IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_sims_imsi ON sims(imsi) WHERE imsi IS NOT NULL"
    )

    # ── 6. device_sims ───────────────────────────────────────────────
    # Many-to-many device <-> SIM with active date range
    op.create_table(
        "device_sims",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("device_id", sa.String(50), nullable=False, index=True),
        sa.Column("sim_id", sa.String(50), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("slot", sa.Integer, nullable=True),
        # physical SIM slot on the device (1, 2, etc.)
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Only one active assignment per SIM at a time
    op.execute(
        "CREATE UNIQUE INDEX uq_device_sims_active_sim "
        "ON device_sims(sim_id) WHERE is_active = true"
    )
    # Only one active SIM per slot per device at a time
    op.execute(
        "CREATE UNIQUE INDEX uq_device_sims_active_slot "
        "ON device_sims(device_id, slot) WHERE is_active = true AND slot IS NOT NULL"
    )

    # ── 7. sim_events ────────────────────────────────────────────────
    op.create_table(
        "sim_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("sim_id", sa.String(50), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        # activate, suspend, resume, terminate, plan_change,
        # assign_device, unassign_device, usage_alert
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        # pending, processing, completed, failed
        sa.Column("initiated_by", sa.String(255), nullable=True),
        # user email or "system"
        sa.Column("details_json", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── 8. sim_usage_daily ───────────────────────────────────────────
    op.create_table(
        "sim_usage_daily",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sim_id", sa.String(50), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("usage_date", sa.Date, nullable=False),
        sa.Column("data_bytes_up", sa.BigInteger, server_default=sa.text("0")),
        sa.Column("data_bytes_down", sa.BigInteger, server_default=sa.text("0")),
        sa.Column("sms_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("voice_seconds", sa.Integer, server_default=sa.text("0")),
        sa.Column("source", sa.String(50), nullable=True),
        # "polled", "webhook", "manual"
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "uq_sim_usage_daily",
        "sim_usage_daily",
        ["sim_id", "usage_date"],
        unique=True,
    )

    # ── 9. jobs ──────────────────────────────────────────────────────
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("queue", sa.String(50), nullable=False, server_default="default"),
        sa.Column("job_type", sa.String(100), nullable=False),
        # e.g. "sim.activate", "webhook.process", "sim.poll_usage",
        # "line.provision_e911"
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        # queued, running, completed, failed, retrying
        sa.Column("payload_json", postgresql.JSONB, nullable=True),
        sa.Column("result_json", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("attempts", sa.Integer, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer, server_default=sa.text("3")),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_jobs_idempotency "
        "ON jobs(idempotency_key) WHERE idempotency_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_jobs_idempotency")
    op.drop_table("jobs")
    op.execute("DROP INDEX IF EXISTS uq_sim_usage_daily")
    op.drop_table("sim_usage_daily")
    op.drop_table("sim_events")
    op.execute("DROP INDEX IF EXISTS uq_device_sims_active_slot")
    op.execute("DROP INDEX IF EXISTS uq_device_sims_active_sim")
    op.drop_table("device_sims")
    op.execute("DROP INDEX IF EXISTS uq_sims_imsi")
    op.execute("DROP INDEX IF EXISTS uq_sims_msisdn")
    op.execute("DROP INDEX IF EXISTS uq_sims_iccid")
    op.drop_table("sims")
    op.drop_table("integration_payloads")
    op.execute("DROP INDEX IF EXISTS uq_integration_status_resource")
    op.drop_table("integration_status")
    op.execute("DROP INDEX IF EXISTS uq_integration_account_tenant")
    op.drop_table("integration_accounts")
    op.drop_table("integrations")
```

**Key design decisions in the migration:**
- `integrations` is a global registry, not tenant-scoped. It defines what integration types the platform supports. Think of it as a catalog.
- `integration_accounts` is tenant-scoped and links a tenant to a specific integration with their own credentials. The `uq_integration_account_tenant` index ensures one account per integration per tenant.
- `sims.iccid` is a required non-nullable unique field (physical SIM identity). `msisdn` and `imsi` are nullable but unique when present.
- `device_sims` uses partial unique indexes to enforce "one active SIM per device slot" and "one active device per SIM" at the database level, avoiding application-level race conditions.
- `jobs.idempotency_key` enables safe retries -- if a caller sends the same key twice, the second insert fails gracefully.
- All indexes use the same `CREATE UNIQUE INDEX ... WHERE` pattern established in migration 006.

---

## 3. Job System Architecture

### 3.1 Infrastructure

**New dependencies** added to `api/requirements.txt`:
```
redis==5.0.0
rq==1.16.0
httpx==0.27.0
```

`redis` -- Python client for Redis.
`rq` -- Redis Queue, a lightweight job queue. Chosen over Celery because it has fewer dependencies, simpler configuration, and this project values minimizing new dependencies. RQ is sufficient for the volume here.
`httpx` -- Async HTTP client for provider API calls. Chosen over `requests` because it supports async/await natively, matching the FastAPI/SQLAlchemy async patterns already in use.

### 3.2 Config Addition

In `api/app/config.py`, add to the `Settings` class:

```python
REDIS_URL: str = "redis://localhost:6379/0"
```

### 3.3 Queue Names and Routing

| Queue Name | Purpose | Concurrency | Timeout |
|------------|---------|-------------|---------|
| `default` | General jobs: webhook processing, status updates | 3 workers | 120s |
| `provisioning` | SIM activate/suspend/resume/terminate, line provisioning | 2 workers | 300s |
| `polling` | Usage polling, status sync (scheduled/batch) | 1 worker | 600s |

In production on Render Starter, a single worker process listening to all three queues is sufficient. The queue names exist for logical separation and to allow future scaling.

### 3.4 Retry Policy

Exponential backoff with jitter:

```
delay = min(base_delay * (2 ** attempt) + random_jitter, max_delay)
```

- `base_delay`: 10 seconds
- `max_delay`: 300 seconds (5 minutes)
- `max_attempts`: 3 (configurable per job type)
- `jitter`: random 0-5 seconds

Retries are tracked in the `jobs` table. When a job fails and `attempts < max_attempts`, the worker:
1. Updates `jobs.status = 'retrying'`, increments `jobs.attempts`
2. Re-enqueues with calculated delay via `rq`'s `enqueue_in`
3. On final failure, sets `jobs.status = 'failed'`, writes `jobs.error`

### 3.5 Worker Entry Point

File: `api/worker.py`

```python
"""RQ worker entry point.

Run: python -m worker
"""
import logging
import redis
from rq import Worker

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("true911.worker")

QUEUES = ["default", "provisioning", "polling"]


def main():
    conn = redis.from_url(settings.REDIS_URL)
    worker = Worker(QUEUES, connection=conn, name="true911-worker")
    logger.info("Starting worker on queues: %s", QUEUES)
    worker.work()


if __name__ == "__main__":
    main()
```

### 3.6 Job Flow Diagram

```
[API Request] --> [Router] --> [Service Layer]
                                     |
                                     v
                            [Create Job row (status=queued)]
                                     |
                                     v
                            [Enqueue to Redis/RQ]
                                     |
                                     v
                        [Worker picks up job]
                                     |
                                     v
                        [Update Job row (status=running)]
                                     |
                                     v
                  [Call Provider Client method]
                      /                    \
                 [success]              [failure]
                     |                      |
                     v                      v
         [Job status=completed]    [Retry? -> re-enqueue]
         [Write sim_event/          [Final failure -> status=failed]
          integration_status]       [Write error to job row]
```

### 3.7 Job Execution Pattern

Each job type maps to a handler function in the integrations/services layer. The worker dispatches based on `job_type`:

```python
# Inside the worker dispatch logic
JOB_HANDLERS = {
    "sim.activate": sim_service.handle_activate,
    "sim.suspend": sim_service.handle_suspend,
    "sim.resume": sim_service.handle_resume,
    "sim.terminate": sim_service.handle_terminate,
    "sim.plan_change": sim_service.handle_plan_change,
    "sim.poll_usage": sim_service.handle_poll_usage,
    "line.provision_e911": line_service.handle_provision_e911,
    "line.sync_did": line_service.handle_sync_did,
    "webhook.process": webhook_service.handle_process_webhook,
}
```

Each handler receives the `job_id` string, loads the job row from the database to get `payload_json`, executes the provider call, and writes results back. This keeps the RQ payload minimal (just the job_id string) and the full payload in Postgres for auditability.

---

## 4. Provider Client Class Hierarchy

All provider clients live in `api/app/integrations/`.

### 4.1 Base Client

File: `api/app/integrations/base.py`

```python
"""Abstract base for provider API clients."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("true911.integrations")

DEFAULT_TIMEOUT = 30.0  # seconds
MAX_TIMEOUT = 120.0


class ProviderClientError(Exception):
    """Raised when a provider API call fails."""
    def __init__(self, status_code: int | None, message: str, response_body: Any = None):
        self.status_code = status_code
        self.message = message
        self.response_body = response_body
        super().__init__(message)


class BaseProviderClient(ABC):
    """Base class for all provider API clients.

    Provides:
    - httpx async client with timeout
    - Idempotency key generation
    - Request/response logging
    - Standardized error handling
    """

    provider_slug: str = ""  # Override in subclass

    def __init__(self, base_url: str, api_key: str, api_secret: str | None = None,
                 timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = min(timeout, MAX_TIMEOUT)

    def _idempotency_key(self) -> str:
        """Generate a unique idempotency key for this request."""
        return f"t91-{uuid.uuid4().hex}"

    def _auth_headers(self) -> dict[str, str]:
        """Return authentication headers. Override per provider."""
        return {"Authorization": f"Bearer {self.api_key}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        idempotency_key: str | None = None,
        timeout: float | None = None,
    ) -> dict:
        """Execute an HTTP request to the provider API.

        Returns the parsed JSON response body.
        Raises ProviderClientError on non-2xx responses.
        """
        url = f"{self.base_url}{path}"
        headers = self._auth_headers()
        headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        effective_timeout = timeout or self.timeout

        async with httpx.AsyncClient(timeout=effective_timeout) as client:
            logger.info("[%s] %s %s", self.provider_slug, method, url)
            response = await client.request(
                method, url, json=json, params=params, headers=headers,
            )

        if response.status_code >= 400:
            body = response.text
            try:
                body = response.json()
            except Exception:
                pass
            logger.error(
                "[%s] %s %s -> %d: %s",
                self.provider_slug, method, url, response.status_code, body,
            )
            raise ProviderClientError(
                status_code=response.status_code,
                message=f"{self.provider_slug} API error: {response.status_code}",
                response_body=body,
            )

        return response.json() if response.text else {}

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify connectivity to the provider. Returns True if reachable."""
        ...
```

**Design notes:**
- `httpx.AsyncClient` is created per-request (short-lived), avoiding connection pool staleness in the worker context. For high-volume paths in the future, a persistent client can be injected.
- `_idempotency_key` generates a UUID-based key. Provider clients that support idempotency (Telnyx does) pass this header automatically.
- `ProviderClientError` wraps non-2xx responses with the status code and body, enabling the service layer to decide on retry logic.

### 4.2 TelnyxClient

File: `api/app/integrations/telnyx.py`

```python
"""Telnyx API client."""

from app.integrations.base import BaseProviderClient


class TelnyxClient(BaseProviderClient):
    provider_slug = "telnyx"

    def __init__(self, api_key: str, **kwargs):
        super().__init__(
            base_url="https://api.telnyx.com/v2",
            api_key=api_key,
            **kwargs,
        )

    async def health_check(self) -> bool:
        try:
            await self._request("GET", "/balance")
            return True
        except Exception:
            return False

    async def activate_sim(self, sim_card_id: str) -> dict:
        return await self._request(
            "POST", f"/sim_cards/{sim_card_id}/actions/enable",
            idempotency_key=self._idempotency_key(),
        )

    async def deactivate_sim(self, sim_card_id: str) -> dict:
        return await self._request(
            "POST", f"/sim_cards/{sim_card_id}/actions/disable",
            idempotency_key=self._idempotency_key(),
        )

    async def get_sim_status(self, sim_card_id: str) -> dict:
        return await self._request("GET", f"/sim_cards/{sim_card_id}")

    async def order_phone_number(self, phone_number: str, connection_id: str) -> dict:
        return await self._request(
            "POST", "/number_orders",
            json={
                "phone_numbers": [{"phone_number": phone_number}],
                "connection_id": connection_id,
            },
            idempotency_key=self._idempotency_key(),
        )

    async def create_messaging_profile(self, name: str) -> dict:
        return await self._request(
            "POST", "/messaging_profiles",
            json={"name": name},
            idempotency_key=self._idempotency_key(),
        )

    async def provision_e911(self, phone_number: str, address: dict) -> dict:
        return await self._request(
            "POST", "/phone_numbers/e911",
            json={"phone_number": phone_number, "address": address},
        )
```

### 4.3 VolaClient

File: `api/app/integrations/vola.py`

```python
"""Vola (hardware provisioning) API client."""

from app.integrations.base import BaseProviderClient


class VolaClient(BaseProviderClient):
    provider_slug = "vola"

    def __init__(self, api_key: str, base_url: str = "https://api.vola.io/v1", **kwargs):
        super().__init__(base_url=base_url, api_key=api_key, **kwargs)

    async def health_check(self) -> bool:
        try:
            await self._request("GET", "/ping")
            return True
        except Exception:
            return False

    async def provision_device(self, serial_number: str, config: dict) -> dict:
        return await self._request(
            "POST", "/devices",
            json={"serial_number": serial_number, "config": config},
            idempotency_key=self._idempotency_key(),
        )

    async def get_device_status(self, device_external_id: str) -> dict:
        return await self._request("GET", f"/devices/{device_external_id}")

    async def update_device_config(self, device_external_id: str, config: dict) -> dict:
        return await self._request(
            "PATCH", f"/devices/{device_external_id}",
            json={"config": config},
        )
```

### 4.4 TMobileClient

File: `api/app/integrations/tmobile.py`

```python
"""T-Mobile IoT/SIM management API client."""

from app.integrations.base import BaseProviderClient


class TMobileClient(BaseProviderClient):
    provider_slug = "tmobile"

    def __init__(self, api_key: str, api_secret: str | None = None,
                 base_url: str = "https://api.t-mobile.com/iot/v1", **kwargs):
        super().__init__(
            base_url=base_url, api_key=api_key, api_secret=api_secret, **kwargs,
        )

    def _auth_headers(self) -> dict[str, str]:
        headers = {"X-API-Key": self.api_key}
        if self.api_secret:
            headers["X-API-Secret"] = self.api_secret
        return headers

    async def health_check(self) -> bool:
        try:
            await self._request("GET", "/status")
            return True
        except Exception:
            return False

    async def activate_sim(self, iccid: str, plan: str | None = None) -> dict:
        body = {"iccid": iccid}
        if plan:
            body["plan"] = plan
        return await self._request(
            "POST", "/sims/activate",
            json=body,
            idempotency_key=self._idempotency_key(),
        )

    async def suspend_sim(self, iccid: str) -> dict:
        return await self._request(
            "POST", "/sims/suspend",
            json={"iccid": iccid},
        )

    async def resume_sim(self, iccid: str) -> dict:
        return await self._request(
            "POST", "/sims/resume",
            json={"iccid": iccid},
        )

    async def get_sim_status(self, iccid: str) -> dict:
        return await self._request("GET", f"/sims/{iccid}")

    async def get_usage(self, iccid: str, start_date: str, end_date: str) -> dict:
        return await self._request(
            "GET", f"/sims/{iccid}/usage",
            params={"start_date": start_date, "end_date": end_date},
        )
```

### 4.5 Client Registry

File: `api/app/integrations/registry.py`

```python
"""Provider client factory."""

from __future__ import annotations

from app.integrations.base import BaseProviderClient
from app.integrations.telnyx import TelnyxClient
from app.integrations.vola import VolaClient
from app.integrations.tmobile import TMobileClient

_CLIENT_MAP: dict[str, type[BaseProviderClient]] = {
    "telnyx": TelnyxClient,
    "vola": VolaClient,
    "tmobile": TMobileClient,
}


def get_client(provider_type: str, api_key: str, **kwargs) -> BaseProviderClient:
    """Instantiate the appropriate provider client.

    Raises ValueError if provider_type is not supported.
    """
    cls = _CLIENT_MAP.get(provider_type)
    if cls is None:
        raise ValueError(f"Unsupported provider type: {provider_type}")
    return cls(api_key=api_key, **kwargs)
```

File: `api/app/integrations/__init__.py`

```python
"""Provider integration clients."""

from app.integrations.registry import get_client

__all__ = ["get_client"]
```

---

## 5. Service Layer Design

### 5.1 Job Service

File: `api/app/services/job_service.py`

This service handles creating job rows and enqueuing them to Redis.

```python
"""Job creation and lifecycle management."""

import uuid
from datetime import datetime, timezone

import redis
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.job import Job

_redis_conn = None

def _get_redis():
    global _redis_conn
    if _redis_conn is None:
        _redis_conn = redis.from_url(settings.REDIS_URL)
    return _redis_conn


async def create_and_enqueue(
    db: AsyncSession,
    *,
    tenant_id: str,
    job_type: str,
    payload: dict,
    queue_name: str = "default",
    idempotency_key: str | None = None,
    max_attempts: int = 3,
) -> Job:
    """Create a job row and enqueue it to RQ.

    Returns the Job ORM object after commit.
    """
    job_id = f"job-{uuid.uuid4().hex[:12]}"

    job = Job(
        job_id=job_id,
        tenant_id=tenant_id,
        queue=queue_name,
        job_type=job_type,
        status="queued",
        payload_json=payload,
        max_attempts=max_attempts,
        idempotency_key=idempotency_key,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue to RQ -- worker receives job_id string, looks up the DB row
    q = Queue(queue_name, connection=_get_redis())
    q.enqueue("worker.dispatch_job", job_id, job_timeout=300)

    return job


async def mark_running(db: AsyncSession, job: Job) -> None:
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    job.attempts += 1
    await db.commit()


async def mark_completed(db: AsyncSession, job: Job, result: dict | None = None) -> None:
    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc)
    job.result_json = result
    await db.commit()


async def mark_failed(db: AsyncSession, job: Job, error: str) -> None:
    if job.attempts < job.max_attempts:
        job.status = "retrying"
        job.error = error
        await db.commit()
        # Re-enqueue with exponential backoff
        import random
        delay = min(10 * (2 ** job.attempts) + random.randint(0, 5), 300)
        q = Queue(job.queue, connection=_get_redis())
        q.enqueue_in(
            timedelta(seconds=delay),
            "worker.dispatch_job",
            job.job_id,
            job_timeout=300,
        )
    else:
        job.status = "failed"
        job.error = error
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()
```

### 5.2 SIM Service

File: `api/app/services/sim_service.py`

```python
"""SIM lifecycle operations -- all async, all enqueue jobs."""

import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sim import Sim
from app.models.sim_event import SimEvent
from app.services.job_service import create_and_enqueue


async def activate(db: AsyncSession, sim: Sim, initiated_by: str) -> dict:
    """Enqueue a SIM activation job."""
    event = SimEvent(
        event_id=f"sev-{uuid.uuid4().hex[:12]}",
        sim_id=sim.sim_id,
        tenant_id=sim.tenant_id,
        event_type="activate",
        status="pending",
        initiated_by=initiated_by,
    )
    db.add(event)
    await db.flush()

    job = await create_and_enqueue(
        db,
        tenant_id=sim.tenant_id,
        job_type="sim.activate",
        payload={"sim_id": sim.sim_id, "iccid": sim.iccid,
                 "provider_type": sim.provider_type, "event_id": event.event_id},
        queue_name="provisioning",
    )
    return {"job_id": job.job_id, "event_id": event.event_id}


async def suspend(db: AsyncSession, sim: Sim, initiated_by: str) -> dict:
    """Enqueue a SIM suspension job."""
    event = SimEvent(
        event_id=f"sev-{uuid.uuid4().hex[:12]}",
        sim_id=sim.sim_id,
        tenant_id=sim.tenant_id,
        event_type="suspend",
        status="pending",
        initiated_by=initiated_by,
    )
    db.add(event)
    await db.flush()

    job = await create_and_enqueue(
        db,
        tenant_id=sim.tenant_id,
        job_type="sim.suspend",
        payload={"sim_id": sim.sim_id, "iccid": sim.iccid,
                 "provider_type": sim.provider_type, "event_id": event.event_id},
        queue_name="provisioning",
    )
    return {"job_id": job.job_id, "event_id": event.event_id}


# resume, terminate, plan_change follow identical pattern
# poll_usage enqueues to "polling" queue with job_type="sim.poll_usage"
```

The `handle_activate` function (called by the worker) would:
1. Load the job row from the database
2. Resolve the integration_account for the tenant + provider_type
3. Decrypt the API key (or read from the account config)
4. Instantiate the provider client via `get_client(provider_type, api_key)`
5. Call `client.activate_sim(iccid)`
6. On success: update `sim.status = 'active'`, `sim_event.status = 'completed'`, `integration_status.sync_state = 'synced'`
7. On failure: let the job retry logic handle it

### 5.3 Line Service

File: `api/app/services/line_service.py`

Follows identical pattern to SIM service:

```python
async def provision_e911(db: AsyncSession, line: Line, initiated_by: str) -> dict:
    """Enqueue an E911 provisioning job for a line."""
    job = await create_and_enqueue(
        db,
        tenant_id=line.tenant_id,
        job_type="line.provision_e911",
        payload={
            "line_id": line.line_id,
            "did": line.did,
            "provider": line.provider,
            "address": {
                "street": line.e911_street,
                "city": line.e911_city,
                "state": line.e911_state,
                "zip": line.e911_zip,
            },
        },
        queue_name="provisioning",
    )
    return {"job_id": job.job_id}


async def sync_did(db: AsyncSession, line: Line, initiated_by: str) -> dict:
    """Enqueue a DID sync job for a line."""
    job = await create_and_enqueue(
        db,
        tenant_id=line.tenant_id,
        job_type="line.sync_did",
        payload={"line_id": line.line_id, "did": line.did, "provider": line.provider},
        queue_name="default",
    )
    return {"job_id": job.job_id}
```

---

## 6. New Router Endpoints

### 6.1 SIM CRUD Router

File: `api/app/routers/sims.py`

Following the exact pattern from `api/app/routers/devices.py` and `api/app/routers/lines.py`:

| Method | Path | Auth | Permission | Description |
|--------|------|------|------------|-------------|
| GET | `/api/sims` | JWT | any role | List SIMs for tenant, with filters (status, provider_type) |
| GET | `/api/sims/{sim_pk}` | JWT | any role | Get single SIM |
| POST | `/api/sims` | JWT | MANAGE_SIMS | Create SIM in inventory |
| PATCH | `/api/sims/{sim_pk}` | JWT | MANAGE_SIMS | Update SIM fields |
| DELETE | `/api/sims/{sim_pk}` | JWT | MANAGE_SIMS | Soft-delete (status -> terminated) |
| POST | `/api/sims/{sim_pk}/assign` | JWT | MANAGE_SIMS | Assign SIM to device (creates device_sim row) |
| POST | `/api/sims/{sim_pk}/unassign` | JWT | MANAGE_SIMS | Unassign SIM from device (sets is_active=false, unassigned_at) |
| POST | `/api/sims/{sim_pk}/activate` | JWT | MANAGE_SIMS | Trigger async activation (enqueues job, returns job_id) |
| POST | `/api/sims/{sim_pk}/suspend` | JWT | MANAGE_SIMS | Trigger async suspension |
| POST | `/api/sims/{sim_pk}/resume` | JWT | MANAGE_SIMS | Trigger async resume |

**Assign endpoint body schema:**
```python
class SimAssign(BaseModel):
    device_id: str
    slot: int | None = None
```

**Assign endpoint logic (within the router):**
1. Verify SIM exists and belongs to tenant
2. Verify device exists and belongs to tenant
3. Check no active assignment exists for this SIM (query `device_sims WHERE sim_id = X AND is_active = true`)
4. If slot is provided, check no active assignment for that device+slot
5. Create `DeviceSim` row
6. Return 201 with the assignment info

### 6.2 Webhook Ingress Router

File: `api/app/routers/webhooks.py`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/webhooks/telnyx` | None (signature verification) | Receive Telnyx webhook |
| POST | `/api/webhooks/vola` | None (signature verification) | Receive Vola webhook |
| POST | `/api/webhooks/tmobile` | None (signature verification) | Receive T-Mobile webhook |

Each endpoint follows this pattern:

```python
@router.post("/telnyx", status_code=202)
async def telnyx_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive and queue a Telnyx webhook for processing."""
    body = await request.json()
    headers = dict(request.headers)

    # TODO: Verify Telnyx signature (stub for now)
    # telnyx_signature = headers.get("telnyx-signature-ed25519")
    # _verify_telnyx_signature(body, telnyx_signature, timestamp)

    # Persist raw payload
    payload = IntegrationPayload(
        payload_id=f"wh-{uuid.uuid4().hex[:12]}",
        integration_slug="telnyx",
        direction="inbound",
        event_type=body.get("data", {}).get("event_type"),
        http_method="POST",
        headers_json=headers,
        body_json=body,
    )
    db.add(payload)
    await db.flush()

    # Enqueue processing job
    await create_and_enqueue(
        db,
        tenant_id="__pending__",  # resolved during processing
        job_type="webhook.process",
        payload={"payload_id": payload.payload_id, "integration_slug": "telnyx"},
        queue_name="default",
    )

    return {"status": "accepted", "payload_id": payload.payload_id}
```

**Signature verification** is stubbed initially. Each provider will have a helper function that can be enabled when the webhook secret is configured in the integration_account:
- Telnyx: Ed25519 signature in `telnyx-signature-ed25519` header
- Vola: HMAC-SHA256 in `X-Vola-Signature` header
- T-Mobile: API key in `X-Webhook-Secret` header

The endpoints always return 202 Accepted immediately. Processing happens asynchronously in the worker.

### 6.3 Jobs Router

File: `api/app/routers/jobs.py`

| Method | Path | Auth | Permission | Description |
|--------|------|------|------------|-------------|
| GET | `/api/jobs` | JWT | VIEW_JOBS | List jobs for tenant with filters (status, job_type, queue) |
| GET | `/api/jobs/{job_pk}` | JWT | VIEW_JOBS | Get single job with result/error detail |

This follows the exact same pattern as the events router. Admin and Manager can view job status.

### 6.4 Router Registration in main.py

Add to `api/app/main.py`:

```python
from .routers import sims, webhooks, jobs

# ... after existing router registrations:
app.include_router(sims.router, prefix="/api/sims", tags=["sims"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
```

---

## 7. Render Config Changes

### 7.1 Updated `render.yaml`

```yaml
databases:
  - name: true911-db
    plan: starter
    databaseName: true911
    postgresMajorVersion: 16

services:
  # FastAPI Backend
  - type: web
    name: true911-api
    runtime: python
    plan: starter
    rootDir: api
    buildCommand: pip install -r requirements.txt
    startCommand: alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /api/health
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: true911-db
          property: connectionString
      - key: JWT_SECRET
        generateValue: true
      - key: CORS_ORIGINS
        value: "https://true911-web-demo.onrender.com,https://true911-web-prod.onrender.com"
      - key: APP_MODE
        value: production
      - key: REDIS_URL
        fromService:
          type: redis
          name: true911-redis
          property: connectionString

  # Background Worker
  - type: worker
    name: true911-worker
    runtime: python
    plan: starter
    rootDir: api
    buildCommand: pip install -r requirements.txt
    startCommand: python -m worker
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: true911-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          type: redis
          name: true911-redis
          property: connectionString
      - key: APP_MODE
        value: production

  # React Frontend (Static Site)
  - type: web
    name: true911-web-prod
    runtime: static
    plan: starter
    rootDir: web
    buildCommand: npm install && npm run build
    staticPublishPath: dist
    headers:
      - path: /*
        name: Cache-Control
        value: public, max-age=0, must-revalidate
    routes:
      - type: rewrite
        source: /*
        destination: /index.html
    envVars:
      - key: VITE_API_URL
        value: https://true911-api.onrender.com/api
      - key: VITE_APP_MODE
        value: production

# Redis
  - type: redis
    name: true911-redis
    plan: starter
    maxmemoryPolicy: allkeys-lru
```

### 7.2 New Environment Variables

| Variable | Service | Value |
|----------|---------|-------|
| `REDIS_URL` | true911-api, true911-worker | Auto-populated from true911-redis |
| `DATABASE_URL` | true911-worker | Same Postgres connection as API |
| `APP_MODE` | true911-worker | `production` |

### 7.3 Cost Impact

On Render Starter:
- Redis Starter: $0/month (free tier, 25MB)
- Worker Starter: $0/month (free tier, limited to 750 hours)

For production scaling, upgrade to paid tiers when webhook volume increases.

---

## 8. RBAC Updates

Add to `api/app/services/rbac.py`:

```python
PERMISSIONS: dict[str, list[str]] = {
    # ... existing permissions ...
    "MANAGE_SIMS": ["Admin"],
    "VIEW_JOBS": ["Admin", "Manager"],
    "MANAGE_INTEGRATIONS": ["Admin"],
}
```

---

## 9. Model Definitions (ORM)

All models follow the exact pattern from existing models: `Base` from `database.py`, `Mapped`/`mapped_column`, `DateTime(timezone=True)`, `server_default=func.now()`.

### 9.1 `api/app/models/sim.py`

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Sim(Base):
    __tablename__ = "sims"

    id: Mapped[int] = mapped_column(primary_key=True)
    sim_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    iccid: Mapped[str] = mapped_column(String(30))
    msisdn: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    imsi: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    provider_type: Mapped[str] = mapped_column(String(50))
    plan_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="inventory")
    activation_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

### 9.2 `api/app/models/job.py`

```python
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    queue: Mapped[str] = mapped_column(String(50), default="default")
    job_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    payload_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    result_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

The remaining models (`Integration`, `IntegrationAccount`, `IntegrationStatus`, `IntegrationPayload`, `DeviceSim`, `SimEvent`, `SimUsageDaily`) follow identical ORM patterns, mapping 1:1 to the migration columns defined in section 2.

### 9.3 `api/app/models/__init__.py` Update

Add imports for all 8 new models:

```python
from app.models.integration import Integration
from app.models.integration_account import IntegrationAccount
from app.models.integration_status import IntegrationStatus
from app.models.integration_payload import IntegrationPayload
from app.models.sim import Sim
from app.models.device_sim import DeviceSim
from app.models.sim_event import SimEvent
from app.models.sim_usage_daily import SimUsageDaily
from app.models.job import Job
```

---

## 10. Pydantic Schemas

### 10.1 `api/app/schemas/sim.py`

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SimOut(BaseModel):
    id: int
    sim_id: str
    tenant_id: str
    iccid: str
    msisdn: Optional[str] = None
    imsi: Optional[str] = None
    provider_type: str
    plan_name: Optional[str] = None
    status: str
    activation_date: Optional[datetime] = None
    notes: Optional[str] = None
    metadata_json: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SimCreate(BaseModel):
    sim_id: str
    iccid: str
    msisdn: Optional[str] = None
    imsi: Optional[str] = None
    provider_type: str
    plan_name: Optional[str] = None
    status: str = "inventory"
    notes: Optional[str] = None
    metadata_json: Optional[dict] = None


class SimUpdate(BaseModel):
    msisdn: Optional[str] = None
    imsi: Optional[str] = None
    provider_type: Optional[str] = None
    plan_name: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    metadata_json: Optional[dict] = None


class SimAssign(BaseModel):
    device_id: str
    slot: Optional[int] = None


class SimActionOut(BaseModel):
    """Returned from async action endpoints (activate, suspend, resume)."""
    job_id: str
    event_id: Optional[str] = None
    message: str
```

### 10.2 `api/app/schemas/job.py`

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class JobOut(BaseModel):
    id: int
    job_id: str
    tenant_id: str
    queue: str
    job_type: str
    status: str
    error: Optional[str] = None
    attempts: int
    max_attempts: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class JobDetailOut(JobOut):
    """Extended view including payload and result (Admin only)."""
    payload_json: Optional[dict] = None
    result_json: Optional[dict] = None
```

---

## 11. Reports RBAC Verification

The current RBAC matrix already has `GENERATE_REPORT` restricted to `["Admin", "Manager"]`. The User role is excluded. The backend enforcement is in place via `require_permission("GENERATE_REPORT")` in the reports endpoint (if it exists in `actions.py` or will be created). The frontend `AuthContext.jsx` mirrors this. No backend change is needed here, but during implementation, verify that any reports-related endpoint uses `dependencies=[Depends(require_permission("GENERATE_REPORT"))]`.

---

## 12. Onboarding Wizard Data Sources

The hardware_models table (migration 006) is already in place and the `GET /api/hardware-models` endpoint is already public (no auth required, suitable for onboarding). The providers endpoint `GET /api/providers` requires auth and returns tenant-scoped providers.

To fully remove hardcoded PR12 references:
1. Check `api/app/adapters/registry.py` -- the PR12 adapter remains valid; it is device-type specific and does not leak to onboarding
2. Check the seed data for any hardcoded "PR12" device types that should reference `hardware_models.id` instead
3. Frontend onboarding wizard should call `GET /api/hardware-models` for device type dropdown (frontend change, not backend)

---

## 13. Test Plan

### 13.1 Migration Verification

```bash
# Apply migration (idempotent -- safe to run multiple times)
cd api && alembic upgrade head

# Verify tables exist
psql $DATABASE_URL -c "\dt sims"
psql $DATABASE_URL -c "\dt jobs"
psql $DATABASE_URL -c "\dt integration_accounts"
psql $DATABASE_URL -c "\dt device_sims"
psql $DATABASE_URL -c "\dt sim_events"
psql $DATABASE_URL -c "\dt sim_usage_daily"
psql $DATABASE_URL -c "\dt integration_status"
psql $DATABASE_URL -c "\dt integration_payloads"
psql $DATABASE_URL -c "\dt integrations"

# Verify unique indexes
psql $DATABASE_URL -c "\di uq_sims_iccid"
psql $DATABASE_URL -c "\di uq_sims_msisdn"
psql $DATABASE_URL -c "\di uq_device_sims_active_sim"
psql $DATABASE_URL -c "\di uq_jobs_idempotency"
```

### 13.2 SIM CRUD

```bash
# Get a token first
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@true911.com","password":"admin123"}' | jq -r '.access_token')

# Create a SIM
curl -s -X POST http://localhost:8000/api/sims \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sim_id": "SIM-001",
    "iccid": "89012345678901234567",
    "msisdn": "+15551234567",
    "provider_type": "telnyx",
    "plan_name": "IoT Basic",
    "status": "inventory"
  }' | jq .

# List SIMs
curl -s http://localhost:8000/api/sims \
  -H "Authorization: Bearer $TOKEN" | jq .

# Get single SIM
curl -s http://localhost:8000/api/sims/1 \
  -H "Authorization: Bearer $TOKEN" | jq .

# Update SIM
curl -s -X PATCH http://localhost:8000/api/sims/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plan_name": "IoT Pro", "notes": "Upgraded plan"}' | jq .

# Duplicate ICCID should fail with 409
curl -s -X POST http://localhost:8000/api/sims \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sim_id": "SIM-002",
    "iccid": "89012345678901234567",
    "provider_type": "tmobile"
  }' | jq .
# Expected: 409 Conflict
```

### 13.3 SIM Assignment

```bash
# Assign SIM to device
curl -s -X POST http://localhost:8000/api/sims/1/assign \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"device_id": "DEV-001", "slot": 1}' | jq .

# Duplicate active assignment should fail
curl -s -X POST http://localhost:8000/api/sims/1/assign \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"device_id": "DEV-002"}' | jq .
# Expected: 409 Conflict ("SIM is already assigned")

# Unassign
curl -s -X POST http://localhost:8000/api/sims/1/unassign \
  -H "Authorization: Bearer $TOKEN" | jq .
```

### 13.4 Webhook Ingress

```bash
# Telnyx webhook (no auth needed)
curl -s -X POST http://localhost:8000/api/webhooks/telnyx \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "event_type": "sim_card.updated",
      "id": "uuid-from-telnyx",
      "payload": {"iccid": "89012345678901234567", "status": "active"}
    }
  }' | jq .
# Expected: 202 with payload_id

# Verify payload was stored
curl -s http://localhost:8000/api/jobs?job_type=webhook.process \
  -H "Authorization: Bearer $TOKEN" | jq .
```

### 13.5 SIM Actions (Async Operations)

```bash
# Activate SIM (enqueues job)
curl -s -X POST http://localhost:8000/api/sims/1/activate \
  -H "Authorization: Bearer $TOKEN" | jq .
# Expected: 202 with {job_id, event_id, message}

# Check job status
curl -s http://localhost:8000/api/jobs/1 \
  -H "Authorization: Bearer $TOKEN" | jq .
# Without Redis/worker running, job stays in "queued"
```

### 13.6 Jobs Endpoint

```bash
# List all jobs
curl -s http://localhost:8000/api/jobs \
  -H "Authorization: Bearer $TOKEN" | jq .

# Filter by status
curl -s "http://localhost:8000/api/jobs?status=queued" \
  -H "Authorization: Bearer $TOKEN" | jq .

# User role should get 403
USER_TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@true911.com","password":"user123"}' | jq -r '.access_token')

curl -s http://localhost:8000/api/jobs \
  -H "Authorization: Bearer $USER_TOKEN" | jq .
# Expected: 403
```

### 13.7 Permission Enforcement

```bash
# User role cannot create SIMs
curl -s -X POST http://localhost:8000/api/sims \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sim_id":"X","iccid":"X","provider_type":"telnyx"}' | jq .
# Expected: 403

# Manager cannot create SIMs (MANAGE_SIMS is Admin-only)
MGR_TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"manager@true911.com","password":"manager123"}' | jq -r '.access_token')

curl -s -X POST http://localhost:8000/api/sims \
  -H "Authorization: Bearer $MGR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sim_id":"X","iccid":"X","provider_type":"telnyx"}' | jq .
# Expected: 403
```

---

## 14. Implementation Sequence

The work should be done in this order due to dependencies:

**Phase 1: Foundation (no Redis needed)**
1. Migration 007 -- create all tables
2. All 8 new model files
3. Update `models/__init__.py`
4. Pydantic schemas (sim, job, integration, webhook)
5. RBAC updates

**Phase 2: SIM CRUD (no Redis needed)**
6. SIM router (CRUD + assign/unassign only, no async actions)
7. Register SIM router in main.py
8. Test SIM CRUD with curl

**Phase 3: Integration Client Layer (no Redis needed)**
9. `integrations/base.py`
10. `integrations/telnyx.py`, `vola.py`, `tmobile.py`
11. `integrations/registry.py`
12. Add `httpx` to requirements.txt

**Phase 4: Job System (requires Redis)**
13. Add `redis`, `rq` to requirements.txt
14. Add `REDIS_URL` to config.py
15. `services/job_service.py`
16. `worker.py`
17. Jobs router
18. Register jobs router in main.py
19. Update render.yaml with Redis + worker

**Phase 5: Async Actions + Webhooks**
20. `services/sim_service.py` (activate, suspend, resume, terminate)
21. `services/line_service.py` (provision_e911, sync_did)
22. Add async action endpoints to SIM router (activate, suspend, resume)
23. Webhook router
24. Register webhook router in main.py

**Phase 6: Polish**
25. Demo seed data for SIMs and integrations
26. Reports RBAC verification
27. Onboarding wizard data source audit
28. End-to-end testing

---

## 15. Potential Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Redis unavailable on Render free tier | Jobs never execute | Phase 2 (SIM CRUD) works without Redis. Jobs can degrade gracefully -- `job_service.create_and_enqueue` catches Redis connection errors and still creates the DB row, letting an admin re-enqueue manually. |
| RQ worker hangs or dies | Jobs pile up in queue | Render auto-restarts worker services. The jobs table shows all queued/failed jobs for debugging. |
| Provider API changes break clients | Integration failures | Each client is isolated; errors are caught by `BaseProviderClient._request` and logged to `integration_payloads`. No cascading failures. |
| Migration 007 is large (9 tables) | Deployment risk | All `CREATE TABLE` operations are additive-only. No existing table is altered. Safe to deploy. Downgrade path drops in reverse order. |
| `device_sims` partial unique index on `is_active` could cause confusion | Orphaned rows | Document that "unassigning" sets `is_active=false` and `unassigned_at`, keeping history. The unique index only constrains active rows. |

---

### Critical Files for Implementation
- `D:/True911_Base44_stuff/true911-prod/api/alembic/versions/007_integration_layer_and_sims.py` - Core migration defining all 9 new tables (must be created first, everything depends on it)
- `D:/True911_Base44_stuff/true911-prod/api/app/integrations/base.py` - BaseProviderClient ABC that all provider clients inherit from (defines the entire HTTP pattern)
- `D:/True911_Base44_stuff/true911-prod/api/app/services/job_service.py` - Job creation + enqueue + retry logic (central orchestrator between routers and worker)
- `D:/True911_Base44_stuff/true911-prod/api/app/routers/sims.py` - SIM CRUD router (largest new router, follows patterns from devices.py and lines.py)
- `D:/True911_Base44_stuff/true911-prod/render.yaml` - Infrastructure config (adds Redis service + worker service to Render deployment)