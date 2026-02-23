/**
 * Drop-in entity wrappers that match the Base44 SDK call signatures.
 *
 * Usage:  import { Site, Incident } from "@/api/entities";
 *         const sites = await Site.list("-last_checkin", 100);
 *         await Site.update(id, { status: "Connected" });
 */

import { apiFetch } from "./client";

function buildQuery(filters = {}, sort, limit) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== null) params.set(k, v);
  });
  if (sort) params.set("sort", sort);
  if (limit) params.set("limit", String(limit));
  return params.toString() ? `?${params}` : "";
}

function makeEntity(basePath) {
  return {
    /** list(sort?, limit?) */
    list(sort, limit) {
      return apiFetch(`${basePath}${buildQuery({}, sort, limit)}`);
    },

    /** filter(filters, sort?, limit?) */
    filter(filters, sort, limit) {
      return apiFetch(`${basePath}${buildQuery(filters, sort, limit)}`);
    },

    /** get(id) */
    get(id) {
      return apiFetch(`${basePath}/${id}`);
    },

    /** create(data) */
    create(data) {
      return apiFetch(basePath, {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    /** update(id, data) */
    update(id, data) {
      return apiFetch(`${basePath}/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    /** delete(id) */
    delete(id) {
      return apiFetch(`${basePath}/${id}`, { method: "DELETE" });
    },
  };
}

export const Site = makeEntity("/sites");
export const TelemetryEvent = makeEntity("/telemetry");
export const ActionAudit = makeEntity("/audits");
export const Incident = makeEntity("/incidents");
export const NotificationRule = makeEntity("/notification-rules");
export const E911ChangeLog = makeEntity("/e911-changes");
export const Device = makeEntity("/devices");
