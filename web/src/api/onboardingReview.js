/**
 * Onboarding Review queue API wrapper (Phase A).
 *
 * Backend contract (see api/app/routers/onboarding_review.py):
 *   GET    /onboarding-reviews                — list + filter (paged)
 *   GET    /onboarding-reviews/export.csv     — CSV download (same filters)
 *   POST   /onboarding-reviews                — create
 *   GET    /onboarding-reviews/{review_id}    — detail
 *   PATCH  /onboarding-reviews/{review_id}    — partial update
 *
 * Reads require VIEW_ONBOARDING_REVIEW; writes require
 * MANAGE_ONBOARDING_REVIEW.  The backend enforces; the page filters the
 * UI to match.
 */

import { apiFetch, getAccessToken } from "./client";
import { config } from "@/config";

function buildQuery(params = {}) {
  const usp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") usp.set(k, v);
  });
  const s = usp.toString();
  return s ? `?${s}` : "";
}

export const OnboardingReviewAPI = {
  /** List/filter the queue.
   *  Filters: status, issue_type, assigned_to, entity_type, priority,
   *           search, limit, offset
   *  Returns: { items: [...], total: N } */
  list(params = {}) {
    return apiFetch(`/onboarding-reviews${buildQuery(params)}`);
  },

  /** Fetch a single review by review_id. */
  get(reviewId) {
    return apiFetch(`/onboarding-reviews/${encodeURIComponent(reviewId)}`);
  },

  /** Create a new review item. */
  create(body) {
    return apiFetch("/onboarding-reviews", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  /** Patch a review.  Any field may be omitted; status transitions to a
   *  terminal value automatically stamp ``resolved_at`` server-side. */
  update(reviewId, body) {
    return apiFetch(`/onboarding-reviews/${encodeURIComponent(reviewId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },

  /** Trigger a CSV download in the browser.
   *
   *  ``apiFetch`` is JSON-only, so we hit the export route directly
   *  with fetch() and feed the blob to an anchor click.  The auth
   *  header is added manually here.
   */
  async exportCsv(params = {}) {
    const url = `${config.apiUrl}/onboarding-reviews/export.csv${buildQuery(params)}`;
    const res = await fetch(url, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${getAccessToken() || ""}`,
      },
    });
    if (!res.ok) {
      throw new Error(`Export failed (${res.status})`);
    }
    const blob = await res.blob();
    const dlUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = dlUrl;
    a.download = `onboarding-reviews-${Date.now()}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(dlUrl);
  },
};
