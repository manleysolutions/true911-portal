# Line Intelligence Engine — Architecture

## What It Is

The Line Intelligence Engine automatically classifies analog line types
connected through ATA (Analog Telephone Adapter) devices and assigns
optimal protocol profiles for SIP/VoIP transport.

**Classification targets:**
- `faccp_contact_id` — fire alarm / intrusion panel Contact ID signalling
- `elevator_voice` — elevator emergency phone (voice, handsfree)
- `fax` — fax machines (T.38 / passthrough)
- `scada_modem` — SCADA / telemetry modem (data passthrough)
- `unknown` — unclassified (safe fallback profile applied)

## How It Fits Into True911 / CSA

```
┌──────────────────────────────────────────────────────┐
│                    True911 Platform                   │
│                                                      │
│  ┌─────────┐  ┌──────────┐  ┌──────────────────┐    │
│  │ Devices │  │  Lines   │  │ Line Intelligence │    │
│  │ (PR12,  │  │ (SIP,    │  │ Engine            │    │
│  │ Telto-  │→ │  POTS,   │→ │ ┌──────────┐     │    │
│  │ nika,   │  │  FXS)    │  │ │ Detector │     │    │
│  │ Flying- │  │          │  │ └────┬─────┘     │    │
│  │ Voice)  │  │          │  │      ↓           │    │
│  └─────────┘  └──────────┘  │ ┌────────────┐   │    │
│                             │ │ Classifier │   │    │
│                             │ └────┬───────┘   │    │
│                             │      ↓           │    │
│                             │ ┌────────────┐   │    │
│                             │ │ Profiles   │   │    │
│                             │ └────────────┘   │    │
│                             └──────────────────┘    │
│                                     ↓               │
│  ┌──────────────┐  ┌───────────────────────────┐    │
│  │ Port States  │  │ LI Events (audit log)     │    │
│  │ (per-port    │  │ classification, adaptation │    │
│  │  tracking)   │  │ override, failure          │    │
│  └──────────────┘  └───────────────────────────┘    │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │ API: /api/line-intelligence/*                │    │
│  │   /status  /ports  /events  /profiles        │    │
│  │   /classify                                  │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

## Module Structure

```
api/app/services/line_intelligence/
├── __init__.py           — Package exports
├── constants.py          — Enums, thresholds
├── models.py             — Pydantic data models (Observation, Classification, Profile, Decision)
├── detector.py           — Signal extraction from Observations
├── classifier.py         — Rule-based scoring → line type + confidence
├── protocol_profiles.py  — Pre-built ATA/SIP profiles per line type
├── session_manager.py    — Pipeline orchestrator
├── adaptation.py         — Abstract interfaces for hardware/SIP integration
├── persistence.py        — Abstract + in-memory persistence backend
├── telemetry.py          — Structured metrics collector
└── ARCHITECTURE.md       — This file

api/app/services/line_intelligence_service.py  — Platform service wrapper
api/app/routers/line_intelligence.py           — API endpoints
api/app/models/line_intelligence_event.py      — ORM: audit log table
api/app/models/port_state.py                   — ORM: per-port state table
api/app/schemas/line_intelligence.py           — Pydantic API schemas
api/alembic/versions/034_line_intelligence.py  — Migration (additive)
```

## Feature Flag

**`FEATURE_LINE_INTELLIGENCE`** (env var, default `"false"`)

When `"false"`:
- All `/api/line-intelligence/*` endpoints return 404
- Engine code is importable but never invoked
- No startup cost, no side effects
- Feature flag visible at `/api/config/features`

When `"true"`:
- Endpoints are active behind standard JWT auth + tenant isolation
- Classification results persisted to `line_intelligence_events` + `port_states`

## Database Tables

### `line_intelligence_events`
Immutable audit log. Each classification, adaptation, override, or failure
produces one row. Indexed by `tenant_id`, `event_type`, `line_id`, `device_id`.

### `port_states`
Mutable per-port tracking. One row per (tenant, device, port_index). Updated
on each new classification. Stores current type, confidence, profile, and
observation count.

Both tables include `tenant_id` for multi-tenant isolation.

## Future Expansion

### Phase 2 — Edge Device Integration
- Implement `ObservationSource` adapters for FlyingVoice TR-069 and Teltonika
- Wire to VOLA `ProfileApplicator` to push ATA configuration
- Real-time observation from SIP event streams

### Phase 3 — Dashboard
- Frontend components for port state visualization
- Classification confidence graphs
- Event timeline

### Phase 4 — Learning / Adaptation
- Re-classification on repeated observations
- Confidence trending
- Optional ML classifier as alternative to rules

### Phase 5 — Cloud Sync
- Edge-to-cloud observation relay
- Centralized profile management
- Fleet-wide analytics
