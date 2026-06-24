# Ops Center Phase 1.5 — Operational Intelligence (Foundations)

> **Authority Level:** 3 — Execution. **Governed by:** `CONSTITUTION.md`.
> Status: **foundations IMPLEMENTED** (additive, inert, flag-gated). Created
> 2026-06-24. Builds on `AI_CUSTOMER_OPERATIONS_CENTER.md` (Phase 1).

## 1. Scope

Phase 1.5 adds the **schema + library scaffolding** for richer Tier-1 support
intelligence. It is **foundations only**:

- **No UI**, **no voice AI**, **no public/customer exposure**.
- **No new HTTP routes** and **no change to the live support workflow** — the
  models and services are not read by anything at runtime yet.
- Everything stays under `FEATURE_OPS_CENTER` (default **OFF**). Because no
  router consumes these foundations, Phase 1.5 is **entirely inert** until a
  later phase opts in; any future endpoint will 404 when the flag is off, per
  the existing module pattern.

A later phase wires these into `escalate`/triage and (eventually, behind the
Phase-3 rate-limiting + policy work) any customer surface.

## 2. What was added

### Enums / constants — `app/services/ops_center/intelligence/constants.py`
- **`IncidentSeverity`** — canonical ladder `critical > high > moderate > low >
  info`. Values intentionally match the existing `incidents.severity` strings
  (the emergency path writes `critical`), so this is a typed view over the same
  vocabulary, not a competing one.
- **`EscalationQueueStatus`** (`queued|assigned|in_progress|resolved|cancelled`),
  **`KnowledgeArticleStatus`** (`draft|published|archived`), **`PlaybookStatus`**
  (`draft|active|retired`), **`ResolutionPatternStatus`**
  (`candidate|confirmed|rejected`).
- **`severity_for_issue(issue_category, is_emergency)`** → default severity per
  Ops Center issue category (emergency ⇒ `critical`); **`priority_for_severity`**
  → numeric queue priority (1 = most urgent).

These are Python string-enums for type safety; persisted columns stay plain
`String` (storing `.value`) per the project's no-native-PG-enum convention.

### Models — `app/models/ops_center_intelligence.py` (migration `049`, additive)
- **`OpsEscalationQueue`** (`ops_escalation_queue`) — queued escalation with
  severity, derived priority, status, assignment, loose links to session/site/device.
- **`OpsKnowledgeArticle`** (`ops_knowledge_articles`) — KB article
  (`tenant_id` nullable ⇒ global/shared); unique `(tenant_id, slug)`.
- **`OpsPlaybook`** (`ops_playbooks`) — ordered `steps` JSONB; unique `(tenant_id, slug)`.
- **`OpsResolutionPattern`** (`ops_resolution_patterns`) — learned
  `signature → recommended_action` with `confidence`/`occurrences`; unique
  `(tenant_id, issue_category, signature)`.

All cross-links are loose strings/UUIDs (no FK) to avoid coupling and migration
ordering issues. Migration `049` is existence-guarded (idempotent) and drops only
its own tables on downgrade. It touches no existing column or table.

### Service stubs — `app/services/ops_center/intelligence/`
- **`escalation_queue.py`** — `build_escalation_entry(session)` /
  `enqueue_escalation(db, session)`: turn a support session into a queue row
  with derived severity + priority. Not yet called by the router.
- **`health_snapshot.py`** — `build_customer_health_snapshot(db, tenant_id)`:
  **read-only**, tenant-scoped rollup (`protected|attention|critical|unknown`)
  from device heartbeats. Degrades to `unknown`/`degraded` with no data. Writes
  nothing. Deliberately thin — the authoritative customer assurance label is the
  Assurance Engine's (`ASSURANCE_ENGINE.md`); this can later delegate to it.
- **`vendor_context.py`** — `build_vendor_context(db, device_id, tenant_id)`:
  a normalized **service output** (`VendorContext` dataclass) describing carrier
  + hardware vendor + transport + identifiers for a device. **Adds no columns**
  to Device/Sim; degrades to `available=False` when the device is unknown.

## 3. Security / safety posture

- **Additive + inert:** no existing table/column changed; nothing reads the new
  models at runtime; no behavior change with the flag off (the default).
- **Tenant-scoped reads:** the health-snapshot and vendor-context services
  filter on `tenant_id`; they never read across tenants.
- **Read-only / no writes** in the service stubs except `enqueue_escalation`
  (which only `add()`s a queue row; the caller commits) — and that is not wired
  to any route yet.
- **No new external calls**, no secrets, no customer/public surface.

## 4. Tests

`api/tests/test_ops_center_intelligence.py` (25 tests): severity-mapping table,
status enums, escalation-entry derivation (incl. emergency ⇒ critical/P1),
`enqueue_escalation`, health-snapshot labels (unknown/protected/critical/
inactive-ignored), vendor-context normalization + graceful degradation, and
model table-name presence.

## 5. Next (later phases, not in this PR)

- Wire `enqueue_escalation` into `escalate`; surface the queue to internal
  operators (still flag-gated, internal-only).
- Seed/author knowledge articles + playbooks; learn resolution patterns from
  resolved sessions.
- Have the health snapshot delegate to the Assurance Engine when enabled.
- Only after Phase-3 rate-limiting/policy: consider any customer-facing read.
