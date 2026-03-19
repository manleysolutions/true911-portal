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

export const Site = {
  ...makeEntity("/sites"),
  missingCoords: () => apiFetch("/sites/missing-coords"),
  geocode: (id) => apiFetch(`/sites/${id}/geocode`, { method: "POST" }),
  bulkGeocode: () => apiFetch("/sites/bulk-geocode", { method: "POST" }),
  fixNumericNames: () => apiFetch("/sites/fix-numeric-names", { method: "POST" }),
};
export const TelemetryEvent = makeEntity("/telemetry");
export const ActionAudit = makeEntity("/audits");
export const Incident = makeEntity("/incidents");
export const NotificationRule = makeEntity("/notification-rules");
export const E911ChangeLog = makeEntity("/e911-changes");
export const Device = makeEntity("/devices");
export const Line = makeEntity("/lines");
export const Recording = makeEntity("/recordings");
export const Event = makeEntity("/events");
export const Provider = makeEntity("/providers");
export const HardwareModel = makeEntity("/hardware-models");
export const Customer = makeEntity("/customers");
export const Sim = makeEntity("/sims");

// VOLA / PR12 integration
export const Vola = {
  testConnection: () => apiFetch("/integrations/vola/test"),
  listOrgs: () => apiFetch("/integrations/vola/orgs"),
  listDevices: (usageStatus = "inUse") =>
    apiFetch(`/integrations/vola/devices?usage_status=${usageStatus}`),
  syncDevices: (usageStatus = "inUse") =>
    apiFetch(`/integrations/vola/devices/sync?usage_status=${usageStatus}`, { method: "POST" }),
  reboot: (deviceSn) =>
    apiFetch(`/integrations/vola/device/${deviceSn}/reboot`, { method: "POST" }),
  readParams: (deviceSn, parameterNames, timeoutSeconds = 20) =>
    apiFetch(`/integrations/vola/device/${deviceSn}/params/read`, {
      method: "POST",
      body: JSON.stringify({ device_sn: deviceSn, parameter_names: parameterNames, timeout_seconds: timeoutSeconds }),
    }),
  writeParams: (deviceSn, parameterValues, timeoutSeconds = 20) =>
    apiFetch(`/integrations/vola/device/${deviceSn}/params/write`, {
      method: "POST",
      body: JSON.stringify({ device_sn: deviceSn, parameter_values: parameterValues, timeout_seconds: timeoutSeconds }),
    }),
  bindToSite: (devicePk, siteId) =>
    apiFetch(`/integrations/vola/device/${devicePk}/bind`, {
      method: "POST",
      body: JSON.stringify({ site_id: siteId }),
    }),
  provisionBasic: (deviceSn, siteCode, informInterval = 300) =>
    apiFetch(`/integrations/vola/device/${deviceSn}/provision/basic`, {
      method: "POST",
      body: JSON.stringify({ device_sn: deviceSn, site_code: siteCode, inform_interval: informInterval }),
    }),
  deviceStatus: (deviceSn) =>
    apiFetch(`/integrations/vola/device/${deviceSn}/status`),
  deploy: (siteId, deviceSns, siteCode, informInterval = 300) =>
    apiFetch("/integrations/vola/deploy", {
      method: "POST",
      body: JSON.stringify({ site_id: siteId, device_sns: deviceSns, site_code: siteCode, inform_interval: informInterval }),
    }),
};
