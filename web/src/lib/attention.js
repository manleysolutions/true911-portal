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

// ── Customer-facing presentation layer ────────────────────────────
//
// Additive layer on top of the canonical engine.  Disambiguates the
// alarming binary "connected | offline" story into five buckets a
// commercial property manager, school IT director, or federal buyer
// can read without alarm bells:
//
//   operational         — telemetry healthy
//   monitoring_pending  — imported / provisioned but no telemetry yet
//                         (never reported AND no critical incident)
//   attention_needed    — known recoverable degradation
//   confirmed_offline   — was reporting, now down OR critical incident
//   integration_pending — explicit "awaiting carrier/API sync"
//                         (reserved; not auto-derived in this layer —
//                         a future backend signal will set this)
//
// Internal roles (Admin / Manager / SuperAdmin / DataSteward /
// DataEntry) keep their existing labels and badges via the existing
// `statusLabel()` / `statusColor()` exports above.  Nothing in this
// block changes their UX.

export const CUSTOMER_STATUS = {
  OPERATIONAL:         "operational",
  MONITORING_PENDING:  "monitoring_pending",
  ATTENTION_NEEDED:    "attention_needed",
  CONFIRMED_OFFLINE:   "confirmed_offline",
  INTEGRATION_PENDING: "integration_pending",
};

const CUSTOMER_LABELS = {
  operational:         "Operational",
  monitoring_pending:  "Monitoring Pending",
  attention_needed:    "Attention Needed",
  confirmed_offline:   "Confirmed Offline",
  integration_pending: "Integration Pending",
};

const CUSTOMER_COLORS = {
  operational: {
    dot: "bg-emerald-500", text: "text-emerald-700",
    bg:  "bg-emerald-50",  border: "border-emerald-200",
  },
  monitoring_pending: {
    // Calm slate — not alarming.  This is the "we have the site,
    // we're waiting for the first heartbeat" state.
    dot: "bg-slate-400", text: "text-slate-700",
    bg:  "bg-slate-50",  border: "border-slate-200",
  },
  attention_needed: {
    dot: "bg-amber-500", text: "text-amber-700",
    bg:  "bg-amber-50",  border: "border-amber-200",
  },
  confirmed_offline: {
    // The ONLY red state on customer surfaces.  Reserved for sites
    // that were previously reporting and have stopped, or sites with
    // a critical incident open.
    dot: "bg-red-500", text: "text-red-700",
    bg:  "bg-red-50",  border: "border-red-200",
  },
  integration_pending: {
    dot: "bg-blue-500", text: "text-blue-700",
    bg:  "bg-blue-50",  border: "border-blue-200",
  },
};

// Roles that see the customer presentation layer.  Internal /
// operations roles fall through to the existing raw labels so admin
// troubleshooting workflows are not degraded.
const CUSTOMER_ROLES = new Set(["User", "Manager"]);

/** True when the given role should see the customer presentation. */
export function isCustomerRole(role) {
  if (!role) return false;
  return CUSTOMER_ROLES.has(role);
}

/**
 * Map a site to one of the five customer-facing buckets.
 *
 * Inputs accepted: anything with `canonical_status` OR a legacy
 * `status` string, plus optional `last_checkin` and
 * `critical_incidents` for the offline-disambiguation rule.
 *
 * Disambiguation: the canonical engine groups never-reported sites
 * AND went-dark sites into `offline`.  For customer surfaces we
 * split those: a site that has never checked in AND has no critical
 * incident is treated as monitoring_pending, not confirmed_offline.
 */
export function toCustomerStatus(site) {
  const canonical = toCanonical(site);

  if (canonical === CANONICAL.CONNECTED) {
    return CUSTOMER_STATUS.OPERATIONAL;
  }
  if (canonical === CANONICAL.ATTENTION) {
    return CUSTOMER_STATUS.ATTENTION_NEEDED;
  }
  if (canonical === CANONICAL.OFFLINE) {
    const everCheckedIn = !!site?.last_checkin;
    const hasCriticalIncident = (site?.critical_incidents ?? 0) > 0;
    if (!everCheckedIn && !hasCriticalIncident) {
      return CUSTOMER_STATUS.MONITORING_PENDING;
    }
    return CUSTOMER_STATUS.CONFIRMED_OFFLINE;
  }
  // unknown / null — friendly default rather than alarming
  return CUSTOMER_STATUS.MONITORING_PENDING;
}

/** Display label for a customer-status key. */
export function customerStatusLabel(key) {
  return CUSTOMER_LABELS[key] || CUSTOMER_LABELS.monitoring_pending;
}

/** Tailwind color tokens for a customer-status key. */
export function customerStatusColor(key) {
  return CUSTOMER_COLORS[key] || CUSTOMER_COLORS.monitoring_pending;
}

/**
 * One-shot helper for badge components.  Returns `null` for internal
 * roles so callers can fall back to the raw StatusBadge — admin
 * workflows are intentionally untouched by this layer.
 */
export function customerSitePresentation(site, role) {
  if (!isCustomerRole(role)) return null;
  const key = toCustomerStatus(site);
  return {
    key,
    label: customerStatusLabel(key),
    ...customerStatusColor(key),
  };
}
