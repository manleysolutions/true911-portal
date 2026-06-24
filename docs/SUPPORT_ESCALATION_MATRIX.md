# Support Escalation Matrix

> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`.
> Companion to `AI_CUSTOMER_OPERATIONS_CENTER.md`. Status: Phase 1 implemented.

## 1. When to escalate

The workflow escalates to a human when it cannot resolve the issue: no
matching asset, no contact on file, failed verification, a critical
diagnostic, an explicit caller request, or any life-safety emergency.

`POST /api/ops-center/session/{id}/escalate` is allowed for **unverified**
sessions on purpose — handoff is the safe fallback when verification can't
complete.

## 2. Handoff summary

`escalate` returns a `HandoffSummary` containing customer, site, device,
service unit, asset label, **identifiers used**, verification result,
diagnostics (only when verified/emergency), and a recommended next action.
This is the "everything the next human needs" packet
(`sessions.build_handoff_summary`).

**Redaction (aligned with the session view):** the summary is built with
`reveal_sensitive = verified OR emergency`. For an **unverified, non-emergency**
escalation the matched **`customer` (tenant)** and **`device_id`** come back
`null` — the operator escalates with `session_ref` and looks the rest up through
normal tenant-scoped tools. Diagnostics are likewise attached only when
verified/emergency. This prevents an unverified caller's *claimed* customer/
device from leaking through the handoff path.

```json
{
  "session_ref": "OPS-3F9A2B1C",
  "issue_category": "no_dial_tone",
  "issue_summary": "No dial tone on elevator phone, Tower A",
  "is_emergency": false,
  "verification_status": "verified",
  "customer": "restoration-hardware",
  "site_id": "RH-YOUNTVILLE",
  "device_id": "dev-1042",
  "service_unit_id": "SU-ELEV-3",
  "asset_label": "Tower A Elevator 3",
  "identifiers_used": ["elevator_phone"],
  "diagnostics": [ /* TriageCheck[] */ ],
  "recommended_next_action": "Confirm line power and ATA registration on site…",
  "handoff_number": "+1…"
}
```

## 3. Issue category → routing

Routing target is the `handoff_number` (request body → `OPS_CENTER_HANDOFF_NUMBER`
default → none). Phase 1 uses a single configurable target; per-category routing
is a Phase 2 extension. Recommended targets:

| Issue category | Severity bias | Suggested target |
|----------------|---------------|------------------|
| `area_of_refuge_issue` | **Life-safety** | Tier-2 life-safety on-call (immediate) |
| `fire_panel_issue` (FACP) | **Life-safety** | Tier-2 life-safety / fire on-call |
| `elevator_phone_issue` | High | Tier-2 voice / field dispatch |
| `no_dial_tone` | High | Tier-2 voice |
| `gate_phone_issue` | Medium | Tier-2 voice |
| `device_offline` | Medium | NOC / device ops |
| `e911_question` | Medium | E911 / compliance desk |
| `location_update` | Low | Data steward / onboarding |
| `billing_question` | Low | Billing (verified only) |
| `general_support` | Low | Tier-1 queue |

## 4. Incident creation

`escalate` opens an `Incident` when `create_incident=true` **or** the session
is an emergency (and none exists yet). Incidents use `source=ops_center`,
`incident_type=<issue_category>`, and `category=life_safety` for the emergency
path (`sessions.create_emergency_incident`). The id (`INC-OPS-…`) is written
back to `session.incident_ref` and surfaced in the escalate response.

`escalation_status`:

- `created` — an incident is linked.
- `requested` — handoff recorded, no incident opened.
- `none` — not yet escalated.

## 5. Emergency override

A declared emergency (`is_emergency=true`) creates the limited life-safety
incident **at session creation**, before any verification, and reveals matched
context to responders. See `SUPPORT_VERIFICATION_WORKFLOW.md` §7.

## 6. Future (Zoho Desk)

The internal AI Support Assistant already integrates Zoho Desk
(`support_escalations.zoho_ticket_*`). A Phase 2+ step can route Operations
Center escalations into the same Zoho Desk department and populate
`ops_support_sessions.ticket_ref`, reusing the existing Desk client.
