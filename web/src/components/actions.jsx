/**
 * Action bus — calls server-side API endpoints.
 * Replaces the old client-side simulation that wrote directly to Base44 entities.
 * All RBAC enforcement and audit trails are now server-side.
 */

import { apiFetch } from "@/api/client";

export function uid(prefix = "ID") {
  return `${prefix}-${Math.random().toString(36).slice(2, 10).toUpperCase()}${Date.now().toString(36).toUpperCase()}`;
}

// ----- PING -----
export async function pingDevice(user, site) {
  return apiFetch("/actions/ping", {
    method: "POST",
    body: JSON.stringify({ site_id: site.site_id }),
  });
}

// ----- REBOOT -----
export async function rebootDevice(user, site) {
  return apiFetch("/actions/reboot", {
    method: "POST",
    body: JSON.stringify({ site_id: site.site_id }),
  });
}

// ----- UPDATE E911 -----
export async function updateE911(user, site, addressData) {
  return apiFetch("/actions/update-e911", {
    method: "POST",
    body: JSON.stringify({ site_id: site.site_id, ...addressData }),
  });
}

// ----- UPDATE HEARTBEAT -----
export async function updateHeartbeat(user, site, frequency) {
  return apiFetch("/actions/update-heartbeat", {
    method: "POST",
    body: JSON.stringify({ site_id: site.site_id, interval_minutes: frequency }),
  });
}

// ----- RESTART CONTAINER -----
export async function restartContainer(user, site, containerName) {
  return apiFetch("/actions/restart-container", {
    method: "POST",
    body: JSON.stringify({ site_id: site.site_id, container_name: containerName }),
  });
}

// ----- PULL CONTAINER LOGS -----
export async function pullContainerLogs(user, site, containerName) {
  return apiFetch("/actions/pull-logs", {
    method: "POST",
    body: JSON.stringify({ site_id: site.site_id, container_name: containerName }),
  });
}

// ----- SWITCH CHANNEL -----
export async function switchChannel(user, site, channel) {
  return apiFetch("/actions/switch-channel", {
    method: "POST",
    body: JSON.stringify({ site_id: site.site_id, channel }),
  });
}

// ----- GENERATE REPORT -----
export async function generateReport(user, params) {
  // Reports are generated client-side (CSV/PDF export)
  // This just creates an audit record server-side
  await apiFetch("/audits", {
    method: "POST",
    body: JSON.stringify({
      audit_id: uid("AUD"),
      request_id: uid("REQ"),
      action_type: "GENERATE_REPORT",
      site_id: null,
      timestamp: new Date().toISOString(),
      result: "success",
      details: `Report generated. ${params?.sections?.join(", ") || ""}`,
    }),
  });
  return { success: true, message: "Report generated successfully." };
}

// ----- ACK INCIDENT -----
export async function ackIncident(user, incident) {
  return apiFetch(`/incidents/${incident.id}/ack`, { method: "POST" });
}

// ----- CLOSE INCIDENT -----
export async function closeIncident(user, incident, notes) {
  return apiFetch(`/incidents/${incident.id}/close`, {
    method: "POST",
    body: JSON.stringify({ resolution_notes: notes || "Closed via portal." }),
  });
}
