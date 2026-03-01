# True911+ Integration Webhooks

## Overview

True911 accepts webhook events from **Zoho CRM** and **QuickBooks** via
HMAC-signed HTTP POST requests. Events are persisted for audit, then
processed asynchronously to normalize data into True911 core models
(Customer, Subscription, Line counts).

A **reconciliation engine** compares deployed lines vs billed lines vs
active subscriptions to detect billing mismatches.

## Configuration

Set these environment variables on the API service:

| Variable | Required | Default | Description |
|---|---|---|---|
| `INTEGRATION_WEBHOOK_SECRET` | **Yes** | (empty) | Shared HMAC-SHA256 secret for signing webhook payloads |
| `INTEGRATION_ALLOWED_SOURCES` | No | `zoho,qb` | Comma-separated list of allowed sources |
| `INTEGRATION_HMAC_SKEW_SECONDS` | No | `300` | Max age (seconds) for replay protection |

For local development, add to `api/.env`:

```
INTEGRATION_WEBHOOK_SECRET=my-local-dev-secret-change-in-prod
```

## Webhook Endpoints

### POST /api/integrations/zoho/webhook
### POST /api/integrations/qb/webhook

Both endpoints accept the same format. The `source` is derived from the URL path.

### Required Headers

| Header | Format | Description |
|---|---|---|
| `X-True911-Signature` | `sha256=<hex>` | HMAC-SHA256 of the raw request body |
| `X-True911-Timestamp` | Unix epoch seconds | Optional replay protection |
| `Content-Type` | `application/json` | Required |

### Signature Computation

```python
import hmac, hashlib
secret = "your-webhook-secret"
body = b'{"event_type":"customer_upsert",...}'
signature = "sha256=" + hmac.new(
    secret.encode(), body, hashlib.sha256
).hexdigest()
```

### Response

All valid requests return **202 Accepted**:

```json
{"accepted": true, "event_id": 42, "job_id": 17}
```

Duplicate deliveries (same `idempotency_key`) return:

```json
{"accepted": true, "duplicate": true, "message": "Event already received"}
```

## Canonical Payload Formats

### customer_upsert

Create or update a customer/account record.

```json
{
  "event_type": "customer_upsert",
  "org_id": "demo",
  "external_account_id": "ZOHO-ACCT-001",
  "name": "Dallas Fire Department",
  "email": "billing@dallasfd.gov",
  "phone": "+12145551234",
  "billing_address": "1234 Main St, Dallas TX 75201",
  "status": "active",
  "idempotency_key": "zoho-cust-001-v3"
}
```

### subscription_upsert

Create or update a subscription. The referenced customer must exist first.

```json
{
  "event_type": "subscription_upsert",
  "org_id": "demo",
  "external_subscription_id": "QB-SUB-001",
  "external_account_id": "ZOHO-ACCT-001",
  "plan_name": "True911 Pro - 5 Lines",
  "status": "active",
  "mrr": 249.95,
  "qty_lines": 5,
  "start_date": "2025-06-01",
  "renewal_date": "2026-06-01",
  "idempotency_key": "qb-sub-001-v2"
}
```

### line_count_update

Update the billed line count on an existing subscription.

```json
{
  "event_type": "line_count_update",
  "org_id": "demo",
  "external_subscription_id": "QB-SUB-001",
  "qty_lines": 7,
  "idempotency_key": "qb-lines-001-v4"
}
```

### Non-canonical payloads

Any `event_type` not in the above list will be stored with status
`needs_mapping`. You can view these in the admin UI under Integration Sync >
Latest Events.

## Example curl Commands

```bash
# Set your secret
SECRET="my-local-dev-secret-change-in-prod"
API="http://localhost:8000"

# 1. Create a customer via Zoho webhook
BODY='{"event_type":"customer_upsert","org_id":"demo","external_account_id":"ZOHO-001","name":"Dallas Fire Dept","email":"billing@dfd.gov","status":"active","idempotency_key":"cust-001"}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

curl -X POST "$API/api/integrations/zoho/webhook" \
  -H "Content-Type: application/json" \
  -H "X-True911-Signature: sha256=$SIG" \
  -H "X-True911-Timestamp: $(date +%s)" \
  -d "$BODY"

# 2. Create a subscription via QuickBooks webhook
BODY='{"event_type":"subscription_upsert","org_id":"demo","external_subscription_id":"QB-SUB-001","external_account_id":"ZOHO-001","plan_name":"Pro 5-Line","status":"active","mrr":249.95,"qty_lines":5,"start_date":"2025-06-01","idempotency_key":"sub-001"}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

curl -X POST "$API/api/integrations/qb/webhook" \
  -H "Content-Type: application/json" \
  -H "X-True911-Signature: sha256=$SIG" \
  -H "X-True911-Timestamp: $(date +%s)" \
  -d "$BODY"

# 3. Trigger reconciliation (requires JWT auth as Admin)
curl -X POST "$API/api/integrations/reconciliation/run" \
  -H "Authorization: Bearer <your-jwt>"

# 4. View latest reconciliation
curl "$API/api/integrations/reconciliation/latest" \
  -H "Authorization: Bearer <your-jwt>"

# 5. View integration events
curl "$API/api/integrations/events?source=zoho&limit=10" \
  -H "Authorization: Bearer <your-jwt>"
```

## Admin UI

Navigate to **Integration Sync** in the sidebar (Admin-only).

- **Latest Events** tab: View all inbound webhook events with source, type,
  status, and error filtering.
- **Reconciliation** tab: View summary cards (customers, subscriptions,
  billed lines, deployed lines, mismatches) and a detailed mismatches table
  with customer filtering. Click "Run Reconciliation" to trigger a fresh
  snapshot.

## Architecture

```
External (Zoho/QB)
  │  POST with HMAC signature
  ▼
/api/integrations/{source}/webhook
  │  Verify HMAC → Parse JSON → Idempotent INSERT → Enqueue Job
  ▼
RQ Worker (integration.process.{source})
  │  Load IntegrationEvent → Route by event_type → Processor
  ▼
Processor (customer_upsert / subscription_upsert / line_count_update)
  │  Upsert via external_*_map tables → Update True911 models
  ▼
True911 Core Models (Customer, Subscription, Line)

Reconciliation (integration.reconcile)
  │  Compare deployed lines vs billed vs active subscriptions
  ▼
ReconciliationSnapshot (results_json with mismatches)
```
