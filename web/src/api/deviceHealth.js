/**
 * Device Health API client (hardware-agnostic).
 *
 * Wraps the read-only /api/device-health endpoints. All calls are
 * tenant-scoped by the backend (the customer only ever sees their own
 * property/device data). The property endpoint returns the SANITIZED
 * customer view — simple language only, no raw vendor/API fields.
 *
 * When FEATURE_DEVICE_HEALTH is off the backend returns 404; callers
 * treat that as "not enabled yet" and render a friendly empty state.
 */

import { apiFetch } from "@/api/client";

/** Global device health for the caller's tenant (includes raw fields — admin use). */
export function getGlobalDeviceHealth() {
  return apiFetch("/device-health");
}

/** Sanitized, simple-language health for one property (site). */
export function getPropertyHealth(siteId) {
  return apiFetch(`/device-health/property/${encodeURIComponent(siteId)}`);
}

/** One service unit's device (admin/detail). */
export function getServiceUnitHealth(unitId) {
  return apiFetch(`/device-health/service-unit/${encodeURIComponent(unitId)}`);
}

/** Vendor adapter status (admin only — MANAGE_INTEGRATIONS). */
export function getAdapterStatus() {
  return apiFetch("/device-health/adapters");
}
