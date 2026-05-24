# LLLM Phase 1 — Rollout & Rollback Notes

Companion to `docs/LLLM_AUDIT_AND_PLAN.md` (architecture) and `docs/AI_OPERATIONAL_SAFETY.md` (governance contract). This document is the **operational runbook** for the Phase 1 PR.

---

## 1. What this PR ships

A read-only, internal-only AI Health Summary surface gated by `FEATURE_LLLM=false` by default. With the default config, this PR is a **no-op deploy** — every existing route, model, migration target, and customer-facing flow behaves identically to before the merge.

| Artifact | Count |
|---|---|
| New backend services | 1 package (`app/services/llm/`) |
| New backend routes | 2 (`GET` + `POST /api/llm/health-summary[/refresh]`) |
| New database tables | 2 (`llm_audit_log`, `llm_summary_cache`) — migration `045` |
| Existing tables modified | 0 |
| Existing routes modified | 0 (only `GET /api/config/features` adds a key) |
| New permission | 1 (`VIEW_AI_SUMMARY` → Admin + SuperAdmin) |
| New env vars | 7 (all default-off / conservative) |
| New tests | 61 |
| Existing tests broken | 0 |

Total test suite after this PR: **1384 pass, 14 warnings (all pre-existing)**.

---

## 2. Pre-merge verification (already completed on this branch)

```bash
# 1. Backend test suite — full pass with zero regressions.
cd api && python -m pytest --tb=short
#   → 1384 passed, 14 warnings in ~10s

# 2. Backend import smoke — app boots and registers the router.
cd api && python -c "from app import main; print(any('/api/llm' in str(r.path) for r in main.app.routes))"
#   → True

# 3. Frontend production build — clean.
cd web && npm run build
#   → 1827 modules transformed, ~30s, no errors.
```

### Manual no-op smoke (perform before merging)

With `FEATURE_LLLM` unset (the default):

```bash
# A. /api/config/features surfaces lllm:false
curl http://localhost:8000/api/config/features
#   Expected: { "samantha": false, "line_intelligence": false, "lllm": false }

# B. The LLM router returns 404 even for SuperAdmin
curl -H "Authorization: Bearer <superadmin-token>" \
     http://localhost:8000/api/llm/health-summary?scope=fleet
#   Expected: HTTP/1.1 404 Not Found

# C. Existing endpoints unchanged (spot-check)
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/sites
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/incidents
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/command/summary
#   Expected: identical responses to pre-Phase-1 behavior.

# D. Frontend with VITE_FEATURE_LLLM unset:
#    - NOC navigation has no "AI Health" entry
#    - Samantha page renders the existing "Coming Soon" stub
#    - Command Center renders no AIHealthSummary card
#    - No /api/llm call appears in browser DevTools Network tab
```

---

## 3. Migration

```bash
# Apply migration 045 in production.  Idempotent — safe to re-run.
cd api && alembic upgrade head
#   → Creates tables llm_audit_log and llm_summary_cache.
#   → Does NOT modify any existing column or table.
#   → The tables stay empty until FEATURE_LLLM is enabled.

# Verify
psql $DATABASE_URL -c "\dt llm_*"
#   Expected:
#     llm_audit_log
#     llm_summary_cache
```

The migration is run automatically by the Render build command (`alembic upgrade head`) on next API deploy. No manual step required.

---

## 4. Enabling the feature (post-merge, after observation period)

### Phase 1a — single-tenant internal soak

```bash
# Backend (Render env vars on true911-api):
FEATURE_LLLM=true
LLLM_ALLOW_EXTERNAL=true        # required for any provider call
LLLM_PROVIDER=anthropic         # explicit (default '' also resolves to anthropic)
ANTHROPIC_API_KEY=<key>         # already exists for the support assistant
LLLM_DAILY_TOKEN_CAP_PER_TENANT=100000   # conservative default
LLLM_PROVIDER_TIMEOUT_SECONDS=5.0
LLLM_CACHE_TTL_SECONDS=300

# Frontend (Render env vars on true911-web-prod):
VITE_FEATURE_LLLM=true
```

Restart both services. Observe:

```bash
# Operator daily review query (Phase 1 soak period)
psql $DATABASE_URL <<'SQL'
SELECT
  date_trunc('hour', created_at) AS hour,
  effective_tenant_id,
  is_impersonating,
  status,
  count(*) AS calls,
  sum(coalesce(tokens_in, 0) + coalesce(tokens_out, 0)) AS tokens,
  round(avg(latency_ms)) AS avg_ms
FROM llm_audit_log
WHERE created_at > now() - interval '24 hours'
GROUP BY 1, 2, 3, 4
ORDER BY 1 DESC;
SQL
```

**Soak duration:** 2 weeks before considering any expansion. During soak only SuperAdmin + internal-tenant Admins can reach the surface (Phase 1 internal-only gate is enforced server-side by `_require_internal_context`).

### Phase 1b — promote to all internal users

After 2 weeks with zero customer-impacting incidents:
- Keep flag on, no env changes.
- Communicate to internal team that the surface is now part of the operator toolbox.

### Phase 1c — DO NOT enable for any customer tenant in Phase 1

Customer rollout is **Phase 3**, gated per-tenant on a new `tenants.settings_json["ai_enabled"]` flag added in that phase. Phase 1 has no mechanism to surface AI output to a customer User/Manager/Admin even with all flags on.

---

## 5. Rollback

### Tier 1 — feature flag flip (preferred, instant)

```bash
# Set on Render and restart:
FEATURE_LLLM=false
# (VITE_FEATURE_LLLM=false on the web service as well, then redeploy)
```

After restart:
- `/api/llm/health-summary` returns 404 immediately.
- No provider call is made.
- No new `llm_audit_log` rows are written.
- Frontend nav entry vanishes; Command card vanishes; Samantha page reverts to "Coming Soon".
- **Historical `llm_audit_log` and `llm_summary_cache` rows are preserved** for post-incident review.

### Tier 2 — revert the PR (if Tier 1 surfaces a regression in unrelated paths)

```bash
git revert <merge-commit-sha>
git push
```

This is safe because:
- Every code change in this PR is additive — no existing function signature, column, or route handler was modified beyond extending `/api/config/features` with one additional key.
- The two new tables remain after a revert (Alembic does not downgrade automatically on a code revert). They are harmless additive state — no foreign key references them.

### Tier 3 — drop the new tables (only if explicitly requested)

```bash
cd api && alembic downgrade -1
#   → Drops llm_audit_log and llm_summary_cache.
#   → Idempotent (table-existence guard).
#   → Permanent — historical audit data is lost.
```

**Do not perform Tier 3 unless** the data in `llm_audit_log` poses a specific governance problem AND a backup has been taken first.

### Verification after rollback

```bash
curl http://<api-host>/api/config/features
#   Expected: lllm: false

curl -H "Authorization: Bearer <superadmin-token>" \
     http://<api-host>/api/llm/health-summary?scope=fleet
#   Expected: HTTP/1.1 404 Not Found

curl -H "Authorization: Bearer <token>" http://<api-host>/api/sites
#   Expected: unchanged 200 with the same shape as before the PR.
```

---

## 6. Operational alerts to set up before Phase 1a soak

- **Audit log growth.** A reasonable upper bound during soak is ~50 audit rows per active internal user per day. Alert if more than 500/day from a single user_email.
- **Fallback rate.** Alert if `status='fallback'` exceeds 25% of calls in any 1-hour window — likely a provider regression or a misconfigured timeout.
- **Token budget exhaustion.** Alert if any tenant hits `status='blocked'` more than 10 times in a 24-hour window — likely indicates the cap is too low for legitimate use.

The queries to power these alerts live in `docs/AI_OPERATIONAL_SAFETY.md` §9.

---

## 7. What this PR explicitly does NOT do

Per `docs/LLLM_AUDIT_AND_PLAN.md` §9 (Constraints):

- No autonomous actions of any kind.
- No conversational memory / chat.
- No customer-facing UI surface.
- No edge-runtime / local-model code.
- No changes to E911, SIP routing, carrier provisioning, or reboot paths.
- No new dependency added to `api/requirements.txt` (Anthropic provider uses httpx, matching existing `support/ai_service.py` pattern).
- No new dependency added to `web/package.json`.
- No vector DB / Redis cache introduced.
- No existing migration touched.
- No existing model / route / schema modified beyond extending `/api/config/features` with one additional key.

---

*End of rollout & rollback notes. Reviewed alongside the Phase 1 PR.*
