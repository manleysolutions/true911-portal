# True911+ Portal — Product & UX Audit

## 1. Current State Assessment

### What Exists
- **Auth**: Login + registration with JWT. Demo mode shows quick-login role picker.
- **Overview**: KPI cards (sites, connected, attention, not connected), fleet health bars, triage queue, recent alerts. Auto-refresh every 30s.
- **Sites**: Searchable table with status filtering. SiteDrawer for detail/actions.
- **Devices**: Table with PR12-specific "Register PR12" modal. IMEI/ICCID/MSISDN fields.
- **Incidents**: Severity/status filtering, ack/close workflow.
- **Notifications**: Rule-based alert system with escalation ladders.
- **Admin**: E911 address editor + heartbeat policy config.
- **Deployment Map**: Leaflet map of site locations.
- **Reports**: 3 preset reports with CSV/PDF export.
- **Containers**: CSA container management (restart, logs, channel switch).
- **Sync Status**: Demo sync event audit log.

### What's Missing / Broken for Production
1. **No voice line management** — customers can't add/track DIDs, SIP registrations, or line status.
2. **No call recordings** — no way to verify call completion or review recordings.
3. **No unified event log** — telemetry is device-centric; no cross-cutting event timeline.
4. **Hardware-locked UX** — "Register PR12" button assumes one device type. ATAs, elevator panels, FACPs not represented.
5. **No onboarding flow** — new customers land on an empty dashboard with no guidance.
6. **E911 buried in Admin** — critical compliance feature hidden behind admin-only page.
7. **No provider abstraction** — no concept of Telnyx/T-Mobile/carrier integrations.
8. **Demo-only pages** — Containers and SyncStatus only work with seed data.
9. **Empty states are missing** — pages with no data show blank tables instead of helpful CTAs.

---

## 2. Revised Information Architecture

```
MAIN NAVIGATION:
  Overview          Dashboard with KPIs + getting started wizard
  Sites             Customer locations / buildings / endpoint locations
  Devices           Edge hardware: PR12, ATA, Digi, ATEL, elevator panels, FACPs
  Lines             Voice lines / DIDs / SIP connections (NEW)
  E911              E911 address management (extracted from Admin)
  Alerts            Notification rules + escalation (renamed from Notifications)
  Recordings        Call recordings by site/device/line (NEW)
  Events            Unified immutable event log (NEW)

SECONDARY:
  Deployment Map    Geographic view
  Incidents         Incident tracking
  Reports           Reporting + exports

ADMIN:
  Settings          Heartbeat policy, system config (renamed from Admin)

FEATURE-FLAGGED:
  AI / Samantha     Coming soon (hidden by default)
```

---

## 3. Onboarding Personas

### Elevator (POTS Replacement)
- **Use case**: Replace copper POTS line in elevator cab with cellular.
- **Day-0**: Install PR12/ATA, activate SIM, provision DID, validate E911, test call button.
- **Day-2**: Monitor heartbeats, review call recordings, handle offline alerts.
- **Key concern**: AHJ (Authority Having Jurisdiction) compliance, call button latency.

### FACP (Fire Alarm Control Panel)
- **Use case**: Replace POTS line for fire alarm monitoring (NFPA 72).
- **Day-0**: Install CSA/ATA at DMARC, configure monitoring line, validate E911, set supervision interval.
- **Day-2**: Monitor supervision heartbeats, handle line-down alerts, verify recording for compliance.
- **Key concern**: NFPA 72 supervision intervals (5-minute rule), dual-line backup.

### Other (Fax, SCADA, Phone)
- **Use case**: General POTS replacement for fax machines, SCADA modems, desk phones.
- **Day-0**: Install device, provision line, basic E911 if needed, configure alerts.
- **Day-2**: Monitor connectivity, review call logs, handle failures.
- **Key concern**: Compatibility, codec support, latency.

---

## 4. Data Model (Hardware + Carrier Agnostic)

### New Tables
- **lines**: Logical voice line / DID / SIP connection. Provider-agnostic (telnyx, tmobile, bandwidth, other).
- **recordings**: Call recording metadata pointers. Provider-agnostic.
- **providers**: Integration config references (Telnyx, T-Mobile, Napco stubs).
- **events**: Unified immutable event log (device.heartbeat, line.down, e911.updated, call.completed, etc.).

### Design Principles
- String types for enums (not Postgres ENUM) — avoids migration churn when adding providers/types.
- Provider is a plain string on lines/recordings, not a FK — keeps it simple.
- Events table supplements telemetry_events — broader scope, cross-cutting.
- All tables use tenant_id for multi-tenancy isolation.

---

## 5. Key Flows

### Day-0 Setup (Onboarding Wizard)
1. Create/select site (address, contact person)
2. Add device (type, manufacturer, model, serial/IMEI/MAC)
3. Add voice line (provider, DID, protocol)
4. Configure E911 address (auto-populates from site)
5. Set up alerts (templates: offline, line down, call button)
6. Review & activate (readiness checklist)

### Day-2 Operations
- Overview dashboard shows fleet health, recent alerts
- Devices table shows last heartbeat, connection status
- Lines table shows SIP registration status, E911 validation
- Events log provides immutable audit trail
- Recordings page shows call history with playback (when provider connected)
- Alerts page manages escalation rules

---

## 6. Implementation Phases

### Phase 1 (This PR): Foundation
- New data model + migrations
- Backend CRUD for lines, recordings, events
- Frontend: Onboarding wizard, Lines/Recordings/Events pages
- Nav restructure, feature flags, polished empty states
- Overview KPIs computed from real data

### Phase 2 (Future): Provider Integration
- Telnyx API: auto-provision DIDs, push E911, pull recordings
- T-Mobile SIM activation API
- Napco monitoring integration

### Phase 3 (Future): AI / Samantha
- AI-assisted onboarding
- Anomaly detection
- Natural language event queries
