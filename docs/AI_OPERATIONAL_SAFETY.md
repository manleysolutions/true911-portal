# AI Operational Safety — True911 + CSAS LLLM

**Authority:** This document is the governance contract for the localized LLM ("LLLM") layer. Code may not behave inconsistently with what is written here without an explicit, signed-off update to this file. Tests in `api/tests/test_llm_*.py` are the enforcement layer.

**Scope:** Phase 1 (read-only AI Health Summary). Customer-facing behavior, autonomous actions, and edge inference are out of scope and explicitly prohibited at this phase. Sections labeled **PHASE 1** are binding now; sections labeled **FUTURE** describe the contract for later phases and may not be implemented yet.

**Companion doc:** `docs/LLLM_AUDIT_AND_PLAN.md` — the phased roadmap and architecture audit this safety contract operationalizes.

---

## 1. Safety Philosophy

The platform serves life-safety communications for managed-POTS replacement, emergency notification, and E911-bound deployments. Any AI behavior that could **delay**, **misroute**, **misreport**, or **silently change** an emergency-relevant signal is unacceptable.

Three rules apply at all phases:

1. **The deterministic floor is mandatory.** Every AI surface has a non-AI fallback that produces a usable response. If the AI layer is removed entirely, the platform must continue operating with degraded (but correct) information.
2. **Audit is non-negotiable.** Every AI invocation produces an audit row. No call is "too small to log." The audit row is the evidence trail for governance review and post-incident analysis.
3. **Tenant isolation is structural, not procedural.** Code paths that could query data must do so through a tenant-scoped factory (`LLLMContext`), never via ad-hoc queries. The structural design is what guarantees isolation, not the developer remembering to filter.

---

## 2. Allowed AI Behaviors

### PHASE 1 — what AI MAY do

- **Summarize** existing structured fields from `sites`, `devices`, `incidents`, `command_telemetry`, and `audit_log_entries` for the caller's tenant only.
- **Explain** what the operator is already seeing in the existing UI — rephrasing numbers into a plain-English paragraph.
- **Recommend** a next step in plain English, drawn from the existing operator runbook patterns (acknowledge incident, check carrier, review device, etc.).
- **Score confidence** in its own output on a `[0.0, 1.0]` scale that the validator clamps and threshold-checks.
- **Use the deterministic fallback** whenever any provider call fails, times out, returns invalid output, or is disabled.
- **Be invoked manually** by an authenticated internal user (Admin or SuperAdmin) via the Samantha page or the Command Center additive card.

### FUTURE — what AI WILL be allowed (later phases, not now)

- **Phase 2:** Local-model diagnostics on the CSAS edge runtime, fully offline, read-only.
- **Phase 3:** Draft support tickets and compliance summaries — human-edited before send.
- **Phase 4:** Human-approved action queue (Admin clicks "Approve" on AI-proposed actions).
- **Phase 5:** Autonomous execution limited to `action_level="safe"` actions (e.g. re-poll a stale device). Never E911, never carrier-write, never reboot.

---

## 3. Prohibited AI Behaviors

The following are forbidden by code and by policy. Any code change that enables one of these requires an explicit update to this section and a corresponding test that confirms the prohibition is removed deliberately.

### Always prohibited (every phase)

- **No autonomous actions on E911 data.** AI may not modify E911 addresses, dispatch routes, or any field tied to PSAP delivery.
- **No carrier provisioning changes.** AI may not activate, suspend, resume, or reconfigure SIMs; may not modify DID assignments; may not change SIP credentials.
- **No call routing changes.** AI may not modify number routing, line state, or trunk configuration.
- **No emergency-behavior changes.** AI may not modify notification rules, escalation ladders, or incident severities.
- **No customer-record writes.** AI may not create, update, or delete `customers`, `sites`, `devices`, `lines`, `users`, or `tenants` rows.
- **No reboot or restart of any device or container.**
- **No invented data.** AI may not surface numbers, identifiers, or facts not present in the structured context. `sources_used` on the response is taken from the context loader, not the provider — provider attempts to invent sources are stripped by the validator.
- **No raw prompt logging with customer data.** Audit rows record `sources_used` references (`"sites:tenant=X"`) but never the actual values that fed the prompt.
- **No LLM call in hot paths.** No AI call in `app/routers/heartbeat.py`, `app/routers/webhooks.py`, provisioning paths, or any high-frequency telemetry processor.
- **No conversational memory.** No persisted multi-turn chat state. Each summary is built from scratch from current structured data.
- **No freeform chat assistant.** AI surfaces are scoped (fleet/site/device summary). Generic Q&A is not a Phase 1 feature.
- **No cross-tenant data access.** A summary call resolved to tenant A may not include any byte from tenant B's tables.
- **No echoing of untrusted content as instructions.** Operator-entered incident summaries and device-reported telemetry are wrapped in `<untrusted_data>` blocks and the model is instructed to never follow instructions inside them. Outputs containing known injection-success markers are rejected.

### Phase 1 specifically prohibited (relaxed in later phases)

- **No customer-facing output.** Phase 1 is internal-only. `customer_safe_summary` on the response is always `null` in Phase 1.
- **No external data egress unless `LLLM_ALLOW_EXTERNAL=true`.** Even when `FEATURE_LLLM=true`, the orchestrator does not call any external provider until this second flag is also set.
- **No edge-model execution.** CSAS runtime does not embed an LLM in Phase 1.

---

## 4. Human Approval Requirements

| Action | Phase 1 | Phase 3 | Phase 4 | Phase 5 |
|---|---|---|---|---|
| Generate summary | No approval | No approval | No approval | No approval |
| Show summary to customer | **Prohibited** | Human edits draft before send | Human edits draft before send | Human edits draft before send |
| Auto-execute remediation | **Prohibited** | **Prohibited** | Admin approves each | Auto only if `action_level="safe"`; everything else needs Admin approval |

In Phase 4 and beyond, "Admin approves" means a row in `support_remediation_actions` with `status="pending"` and `action_level="gated"`, transitioned by an authenticated Admin via a UI click that is itself audited.

---

## 5. Tenant Isolation Guarantees

### Code-level enforcement

- **Single query callsite.** All data queries for an AI summary live in `app/services/llm/context.py` (`LLLMContext`). Other modules in `app/services/llm/` do not import SQLAlchemy. A code-review rule (`grep "select(" app/services/llm/**.py | grep -v context.py` must be empty) is enforced at PR time.
- **Tenant filter is fixed at construction.** `LLLMContext(user, db)` reads `user.tenant_id` once and uses it on every query — callers cannot pass a tenant_id by hand.
- **Cross-tenant site lookup returns `None`.** `load_site(site_id)` filters on `tenant_id == user.tenant_id`, so a `site_id` belonging to a different tenant resolves to "site not found" rather than leaking existence.
- **SuperAdmin impersonation is preserved on the audit row.** `effective_tenant_id` and `original_tenant_id` are stored separately on `llm_audit_log` so the governance question "did a SuperAdmin look at tenant X via impersonation" has a one-line SQL answer.

### Operational expectations

- Operators reviewing the audit log should be able to identify, per tenant, who generated summaries, when, and what they referenced — without ever seeing the actual customer values that fed the summary.
- An auditor must be able to confirm cross-tenant isolation by running an SQL query like `SELECT effective_tenant_id, original_tenant_id, is_impersonating, count(*) FROM llm_audit_log GROUP BY 1,2,3` — anomalies should be visible and rare.

---

## 6. Audit Guarantees

Every call to `/api/llm/health-summary` (GET or POST refresh) writes **exactly one** row to `llm_audit_log` (`api/app/models/llm_audit.py`, migration `045`). The row contains:

| Field | Guarantee |
|---|---|
| `audit_id` | Unique, of the form `ai-<uuid12>`. Also returned to the client as `summary_id`. |
| `user_id`, `user_email`, `user_role` | The authenticated user, recorded as strings so an audit row survives later user deletion / role rename. |
| `effective_tenant_id`, `original_tenant_id`, `is_impersonating` | Whether a SuperAdmin was acting-as a customer tenant when the call was made. |
| `scope`, `scope_id` | What was requested (`fleet`, `site:abc`, `device:xyz`). |
| `model`, `prompt_template_version` | The provider model identifier and the immutable versioned prompt template that produced this row. |
| `sources_used` | A structured JSONB list of `"<table>:<key>"` references — what data the context loader actually read. NEVER the values themselves. |
| `summary_text`, `customer_safe_summary`, `internal_summary` | The generated artifacts. `customer_safe_summary` is always `null` in Phase 1. |
| `confidence` | The validator's clamped confidence score. |
| `tokens_in`, `tokens_out`, `latency_ms` | Provider operational metadata, when available. |
| `status` | `ok` \| `fallback` \| `blocked` \| `error` — captured even when the provider was not reached. |
| `error_summary` | Non-sensitive human-readable reason when status ≠ `ok`. |
| `created_at` | Server timestamp, timezone-aware. |

**Hard rule:** raw prompts are not stored. The audit row plus the immutable prompt template version is sufficient to reproduce any historical call without the row needing to contain customer data.

---

## 7. Fallback Behavior

The orchestrator (`app/services/llm/orchestrator.py`) is engineered so **every code path returns a valid `HealthSummaryResponse`-shaped payload**. There is no error response shape on this surface.

### Fallback triggers (each writes an audit row with `status="fallback"` or `"blocked"`)

1. `FEATURE_LLLM` not exactly `"true"` → router 404s, no fallback row needed.
2. `LLLM_ALLOW_EXTERNAL` not `"true"` → deterministic fallback returned, `error_summary="egress disabled"`.
3. `LLLM_PROVIDER` resolves to an unknown name → deterministic fallback, `error_summary="unknown provider '<x>'"`.
4. Per-tenant daily token cap exceeded → deterministic fallback, `status="blocked"`, `error_summary="daily token cap exceeded"`.
5. Provider returns timeout → deterministic fallback, `error_summary` records timeout duration.
6. Provider returns HTTP 4xx/5xx → deterministic fallback, status code recorded (body NOT echoed — it can leak hints about API keys/orgs).
7. Provider returns malformed JSON or response missing required keys → deterministic fallback.
8. Validator rejects the response (length cap, injection marker, low confidence, missing required field after fallback) → deterministic fallback, `error_summary` records the validator's reason.

### What the deterministic fallback guarantees

- Same response shape and field set as a fresh provider response.
- `deterministic_fallback=true` and `source="fallback"` on the response so the UI and any downstream consumer can tell.
- Confidence reflects coverage of the structured data the rules saw, NOT a statistical claim.
- Never references invented data — every assertion comes from `LLLMContext`-loaded rows.

---

## 8. Escalation Boundaries

### Phase 1
- AI does not escalate. There is no notification to a human triggered by an AI summary in Phase 1.
- An Admin reading a summary may manually open an incident or send a ticket through the existing (non-AI) tools.

### Phase 3+
- AI-drafted ticket bodies will land in the existing `SupportEscalation` table with `was_deduplicated` and `status="pending"` semantics, and will require Admin send.
- Recommended actions surfaced in Phase 4 will land as `support_remediation_actions` rows in `action_level="gated"` status. They are inert until an Admin transitions them.

### Hard rule
- **AI never directly triggers a paging escalation, a phone call, an SMS, or any outbound communication channel** in Phase 1. Phase 3+ only does so through the existing escalation pipeline (Zoho Desk integration, email queue) under explicit human control.

---

## 9. Operator Responsibilities

When the AI feature is enabled in a deployment, the operator-on-call assumes the following responsibilities:

1. **Review the audit log periodically.** `SELECT * FROM llm_audit_log WHERE created_at > now() - interval '24 hours' ORDER BY created_at DESC` is the recommended daily review query during Phase 1 soak.
2. **Treat low-confidence summaries as advisory.** A summary with `confidence < 0.60` or `deterministic_fallback=true` should be cross-checked against the underlying dashboards before action.
3. **Treat AI summaries as triage aid, not as ground truth.** The summary tells you where to look; the underlying device data is what you act on.
4. **Flag false positives and false negatives.** Phase 1 has no built-in feedback loop; report anomalies to engineering via the regular bug-report channel so prompt templates can be revised in v2.
5. **Stop using the feature immediately if you observe a tenant-isolation bug** — surface in any tenant tagged as belonging to another tenant. Set `FEATURE_LLLM=false` and contact engineering.

---

## 10. Kill-Switch Procedure

To disable the entire LLLM surface in a deployment:

```bash
# On the API service (Render):
#   1. Set FEATURE_LLLM=false  (or unset it)
#   2. Restart the service.

# Verification (from any browser or curl):
curl https://<api-host>/api/config/features
#   → { "samantha": ..., "line_intelligence": ..., "lllm": false }

curl -H "Authorization: Bearer <token>" https://<api-host>/api/llm/health-summary?scope=fleet
#   → 404 Not Found
```

After the kill-switch:
- The Samantha page falls back to its "Coming Soon" placeholder.
- The Command Center additive card vanishes.
- No `llm_audit_log` rows are written.
- No provider call is made.
- `llm_audit_log` and `llm_summary_cache` tables remain populated with historical data — they are additive and not dropped by the kill-switch. They can be retained for audit review or truncated manually.

---

## 11. Change Control

Modifications to this document or to the AI safety-critical code paths require:

1. A PR titled `safety: <change>` with a description of why the change is needed.
2. A corresponding test in `api/tests/test_llm_*.py` that asserts the new contract.
3. Review by at least one engineer not on the AI work stream.
4. Update to `docs/LLLM_AUDIT_AND_PLAN.md` if the change affects the phased roadmap.

Reverting a safety provision in this document requires the same change-control path as adding one — there is no "we'll fix it later" exception for prohibited behaviors.

---

## 12. Open Items (will be addressed in Phase 2+)

- Per-tenant `ai_enabled` flag on the `tenants` table (Phase 3 prerequisite for customer rollout).
- Background tidy job for `llm_summary_cache` (Phase 1.1 follow-on).
- Operator dashboard for audit-log review (currently SQL-only).
- Edge-model selection, hardware profiling, and signed-model update channel (Phase 2 prerequisite).
- Compliance report templates (NENA i3 / NG911 — Phase 3 prerequisite).

---

*End of operational safety contract. Last reviewed alongside Phase 1 implementation on the date listed in the PR that introduced this file.*
