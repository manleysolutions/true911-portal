/**
 * Assurance API client (read-only).
 *
 * Wraps GET /api/assurance/site/{id} — tenant-scoped + customer-sanitized by
 * the backend. The backend gates these routes behind FEATURE_ASSURANCE_ENGINE
 * and returns 404 when off; callers treat that as "not enabled" and render a
 * friendly state.
 *
 * There is no backend portfolio endpoint, so the portfolio view aggregates the
 * tenant's sites (existing /sites) with a per-site assurance call. No business
 * logic lives here or in the UI — the label/reasons come from the engine.
 */

import { apiFetch } from "@/api/client";
import { Site } from "@/api/entities";

/** Assurance for one site (full sanitized payload). */
export function getSiteAssurance(siteId) {
  return apiFetch(`/assurance/site/${encodeURIComponent(siteId)}`);
}

function normalizeSites(resp) {
  if (Array.isArray(resp)) return resp;
  if (resp && Array.isArray(resp.items)) return resp.items;
  return [];
}

/**
 * Load the caller-tenant's sites and each site's assurance label.
 *
 * Per-site failures are tolerated: a 404 (engine flag off) or any error maps
 * the row to "Unknown" with an `error` marker, so the dashboard degrades
 * gracefully instead of failing wholesale.
 *
 * Returns an array of:
 *   { site_id, site_name, customer_name, assurance_label, reasons[],
 *     as_of, recommended_action, error }
 */
export async function loadPortfolioAssurance({ limit = 200 } = {}) {
  const sites = normalizeSites(await Site.list("site_name", limit));

  return Promise.all(
    sites.map(async (s) => {
      const siteId = s.site_id || s.siteId;
      const base = {
        site_id: siteId,
        site_name: s.site_name || s.siteName || siteId,
        customer_name: s.customer_name || s.customerName || null,
      };
      try {
        const a = await getSiteAssurance(siteId);
        return {
          ...base,
          assurance_label: a.assurance_label || "Unknown",
          reasons: a.reasons || [],
          as_of: a.as_of || null,
          recommended_action: a.recommended_action || null,
          error: null,
        };
      } catch (e) {
        return {
          ...base,
          assurance_label: "Unknown",
          reasons: [],
          as_of: null,
          recommended_action: null,
          error: e?.status === 404 ? "unavailable" : (e?.message || "error"),
        };
      }
    })
  );
}
