# CSAS True911 Client

Lightweight Python client for the CSAS edge runtime to send heartbeats and line-intelligence observations to the True911 cloud API.

## Requirements

- Python 3.10+
- `requests` library

## Configuration

All settings are read from environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DEVICE_ID` | Yes | — | Device ID registered in True911 |
| `DEVICE_API_KEY` | Yes | — | Device API key (starts with `t91_`) |
| `TRUE911_BASE_URL` | No | `http://localhost:8000` | True911 API base URL |
| `SITE_ID` | No | — | Default site ID for observations |
| `REQUEST_TIMEOUT_SECONDS` | No | `10` | HTTP request timeout |
| `HEARTBEAT_INTERVAL_SECONDS` | No | `60` | Suggested heartbeat interval |
| `LOG_LEVEL` | No | `INFO` | Python log level |

## Usage

### As a library (imported by CSAS runtime)

```python
from edge.csas import True911Client

client = True911Client(
    base_url="https://true911-api.onrender.com",
    device_id="CSAS-001",
    device_api_key="t91_abc123...",
)

# Send heartbeat
result = client.send_heartbeat(
    status="running",
    uptime=86400,
    version="3.1.0",
    extra={"signal_dbm": -78, "sip_status": "registered"},
)

# Send line observation
decision = client.send_observation(
    line_id="line-1",
    port_index=0,
    dtmf_digits="*1234567890#",
    voice_energy_estimate=0.05,
    silence_ratio=0.85,
)
```

### Standalone smoke test

```bash
DEVICE_ID=CSAS-001 \
DEVICE_API_KEY=t91_abc123 \
TRUE911_BASE_URL=https://true911-api.onrender.com \
    python -m edge.csas
```

## Endpoints & Payload Contracts

### Heartbeat: `POST /api/heartbeat`

Header: `X-Device-Key: <DEVICE_API_KEY>`

```json
{
  "device_id": "CSAS-001",
  "status": "running",
  "timestamp": "2026-03-23T12:00:00+00:00",
  "uptime": 86400,
  "version": "3.1.0",
  "signal_dbm": -78,
  "sip_status": "registered"
}
```

Response:
```json
{
  "ok": true,
  "device_id": "CSAS-001",
  "next_heartbeat_seconds": 60
}
```

### Observation: `POST /api/line-intelligence/edge-classify`

Header: `X-Device-Key: <DEVICE_API_KEY>`

```json
{
  "device_id": "CSAS-001",
  "line_id": "line-1",
  "site_id": "site-100",
  "port_index": 0,
  "dtmf_digits": "*1234567890#",
  "fax_tone_present": false,
  "modem_carrier_present": false,
  "voice_energy_estimate": 0.05,
  "silence_ratio": 0.85,
  "window_duration_ms": 5000,
  "source": "csas"
}
```

Response:
```json
{
  "decision_id": "dec-abc123",
  "line_id": "line-1",
  "classification": {
    "line_type": "contact_id",
    "confidence_score": 0.95,
    "confidence_tier": "high",
    "is_actionable": true,
    "fallback_applied": false,
    "evidence": [...]
  },
  "assigned_profile": {
    "profile_id": "prof-cid",
    "profile_name": "Contact ID",
    "line_type": "contact_id"
  },
  "manual_override": false,
  "pipeline_version": "1.0.0"
}
```

## Error Handling

All methods return `None` on failure. The client never raises exceptions for network or HTTP errors — the CSAS runtime continues operating even when the cloud is unreachable.

| HTTP Status | Meaning | Client Behavior |
|-------------|---------|-----------------|
| 200 | Success | Returns parsed JSON |
| 403 | Invalid device credentials | Returns `None`, logs warning |
| 404 | Feature not enabled | Returns `None`, logs warning |
| 500 | Server error | Returns `None`, logs warning |
| Network error | Unreachable | Returns `None`, logs error |

## Running Tests

```bash
cd D:\True911_Base44_stuff\true911-prod
python -m pytest edge/tests/test_true911_client.py -v
```

## Expected Log Output (smoke test)

```
2026-03-23 12:00:00 csas INFO Connecting to https://true911-api.onrender.com as device CSAS-001
2026-03-23 12:00:00 csas.true911_client INFO POST /api/heartbeat → 200
2026-03-23 12:00:00 csas INFO Heartbeat accepted — next in 60s
2026-03-23 12:00:00 csas.true911_client INFO POST /api/line-intelligence/edge-classify → 200
2026-03-23 12:00:00 csas INFO Classification: contact_id (confidence=0.95)
```

When the cloud is unreachable:
```
2026-03-23 12:00:00 csas INFO Connecting to https://true911-api.onrender.com as device CSAS-001
2026-03-23 12:00:00 csas.true911_client ERROR POST /api/heartbeat failed: ConnectionError(...)
2026-03-23 12:00:00 csas WARNING Heartbeat rejected or unreachable
2026-03-23 12:00:00 csas.true911_client ERROR POST /api/line-intelligence/edge-classify failed: ConnectionError(...)
2026-03-23 12:00:00 csas WARNING Observation rejected or unreachable
```
