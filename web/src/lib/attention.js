/**
 * Attention Engine — frontend utilities.
 *
 * Consumes the centralized `data.attention` payload from /command/summary
 * and provides consistent status labels, colors, and helpers across all
 * role-specific dashboards.
 *
 * All status derivation happens on the backend.  These functions handle
 * presentation only — mapping canonical statuses to role-appropriate
 * wording and visual styling.
 */

// ── Canonical status values (must match backend) ──────────────────

export const CANONICAL = {
  CONNECTED: "connected",
  ATTENTION: "attention",
  OFFLINE: "offline",
  UNKNOWN: "unknown",
};

// ── Role-specific labels ──────────────────────────────────────────

const STATUS_LABELS = {
  user: {
    connected: "Working",
    attention: "Needs Attention",
    offline: "Offline",
    unknown: "Unknown",
  },
  manager: {
    connected: "Connected",
    attention: "Attention Needed",
    offline: "Not Connected",
    unknown: "Unknown",
  },
  admin: {
    connected: "Connected",
    attention: "Attention Needed",
    offline: "Not Connected",
    unknown: "Unknown",
  },
  superadmin: {
    connected: "Connected",
    attention: "Attention Needed",
    offline: "Not Connected",
    unknown: "Unknown",
  },
};

/**
 * Get the display label for a canonical status, adjusted for role.
 * @param {string} canonical - one of connected/attention/offline/unknown
 * @param {string} role - user/manager/admin/superadmin
 */
export function statusLabel(canonical, role = "manager") {
  const tier = (role || "manager").toLowerCase();
  const labels = STATUS_LABELS[tier] || STATUS_LABELS.manager;
  return labels[canonical] || canonical || "Unknown";
}

// ── Status colors (shared across all roles) ───────────────────────

export const STATUS_COLORS = {
  connected: {
    dot: "bg-emerald-500",
    text: "text-emerald-600",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    darkDot: "bg-emerald-500",
    darkText: "text-emerald-400",
  },
  attention: {
    dot: "bg-amber-500",
    text: "text-amber-600",
    bg: "bg-amber-50",
    border: "border-amber-200",
    darkDot: "bg-amber-500",
    darkText: "text-amber-400",
  },
  offline: {
    dot: "bg-red-500",
    text: "text-red-600",
    bg: "bg-red-50",
    border: "border-red-200",
    darkDot: "bg-red-500",
    darkText: "text-red-400",
  },
  unknown: {
    dot: "bg-gray-400",
    text: "text-gray-500",
    bg: "bg-gray-50",
    border: "border-gray-200",
    darkDot: "bg-slate-500",
    darkText: "text-slate-400",
  },
};

/**
 * Get color config for a canonical status.
 */
export function statusColor(canonical) {
  return STATUS_COLORS[canonical] || STATUS_COLORS.unknown;
}

// ── Legacy status mapping ─────────────────────────────────────────
// Maps the old DB status strings to canonical values so existing
// site_summaries (which still carry the DB status field) work with
// the new presentation layer.

const LEGACY_MAP = {
  "Connected": CANONICAL.CONNECTED,
  "Attention Needed": CANONICAL.ATTENTION,
  "Not Connected": CANONICAL.OFFLINE,
};

/**
 * Convert a legacy DB status string to a canonical status.
 * If the site already has a canonical_status from the attention engine,
 * prefer that.
 */
export function toCanonical(site) {
  if (site?.canonical_status) return site.canonical_status;
  return LEGACY_MAP[site?.status] || CANONICAL.UNKNOWN;
}

// ── Attention data extraction helpers ─────────────────────────────

/**
 * Extract attention summary counts from the API response.
 * Uses attention engine data if available, falls back to site_summaries.
 */
export function getAttentionCounts(data) {
  const attn = data?.attention?.summary;
  if (attn) {
    return {
      total: attn.total_sites || 0,
      connected: attn.connected || 0,
      attention: attn.attention || 0,
      offline: attn.offline || 0,
      unknown: attn.unknown || 0,
      totalDevices: attn.total_devices || 0,
      devicesOnline: attn.devices_online || 0,
      devicesOffline: attn.devices_offline || 0,
    };
  }

  // Fallback: derive from site_summaries
  const sites = data?.site_summaries || [];
  const offline = sites.filter(s => s.status === "Not Connected").length;
  const attention = sites.filter(s => s.needs_attention && s.status !== "Not Connected").length;
  const connected = sites.length - offline - attention;
  return {
    total: sites.length,
    connected,
    attention,
    offline,
    unknown: 0,
    totalDevices: data?.portfolio?.total_devices || 0,
    devicesOnline: data?.portfolio?.devices_with_telemetry || 0,
    devicesOffline: (data?.portfolio?.stale_devices || 0) + (data?.portfolio?.devices_missing_telemetry || 0),
  };
}

/**
 * Get the attention feed items from the API response.
 * Falls back to deriving from site_summaries + incidents.
 */
export function getAttentionFeed(data) {
  if (data?.attention?.feed?.length >= 0) {
    return data.attention.feed;
  }
  return [];
}

/**
 * Get enriched site list from attention engine.
 * Each site has canonical_status, severity, needs_attention, summaries.
 * Falls back to site_summaries with legacy mapping.
 */
export function getAttentionSites(data) {
  if (data?.attention?.sites?.length >= 0) {
    return data.attention.sites;
  }
  // Fallback: map site_summaries to canonical shape
  return (data?.site_summaries || []).map(s => ({
    ...s,
    canonical_status: LEGACY_MAP[s.status] || CANONICAL.UNKNOWN,
    severity: s.critical_incidents > 0 ? "critical" : s.needs_attention ? "medium" : "info",
    technical_summary: "",
    friendly_summary: "",
  }));
}
