/**
 * LLLM Phase 1 — thin client for /api/llm.
 *
 * All calls go through apiFetch so the JWT, X-Act-As-Tenant header, and
 * the global 401-refresh path are inherited automatically.  No state
 * lives in this module; callers own the result.
 *
 * Every endpoint returns 404 when FEATURE_LLLM is off on the backend,
 * so callers should treat 'not configured' identically to a real 404 —
 * hide the surface rather than show an error.
 */

import { apiFetch } from "@/api/client";

/**
 * Fetch an AI Health Summary.
 *
 * @param {Object} opts
 * @param {"fleet"|"site"|"device"} opts.scope        Defaults to "fleet".
 * @param {string|undefined} opts.scopeId             Required when scope === "site".
 * @param {boolean} opts.forceRefresh                 Bypass the server-side cache.
 * @returns {Promise<Object>} HealthSummaryResponse-shaped payload.
 */
export async function getHealthSummary({
  scope = "fleet",
  scopeId,
  forceRefresh = false,
} = {}) {
  const params = new URLSearchParams({ scope });
  if (scopeId) params.set("scope_id", scopeId);
  if (forceRefresh) params.set("force_refresh", "true");
  return apiFetch(`/llm/health-summary?${params.toString()}`);
}

/**
 * POST variant for the "Refresh" button — bypasses the cache, same
 * audit/permission gates as GET.
 *
 * Provided as a separate verb so an audit reader can distinguish a
 * deliberate refresh from a routine read.
 */
export async function refreshHealthSummary({ scope = "fleet", scopeId } = {}) {
  const params = new URLSearchParams({ scope });
  if (scopeId) params.set("scope_id", scopeId);
  return apiFetch(`/llm/health-summary/refresh?${params.toString()}`, {
    method: "POST",
  });
}
