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
// The True911 customer portal is positioned as a deployment, device,
// and location management platform — NOT a NOC/alarm monitoring
// console.  Customer surfaces therefore use inventory + telemetry
// language, never monitoring language, so we never imply active
// monitoring where live carrier/API telemetry doesn't yet exist.
//
// Five customer-facing buckets:
//
//   reporting           — the device IS sending live telemetry
//   inventory           — the location is registered (and possibly
//                         deployed in the field), but no telemetry
//                         has been received yet.  Neither good nor
//                         bad — just an inventory record.  Reporting
//                         begins once carrier / API integration is in
//                         place and the device emits its first packet.
//   attention_needed    — a specific recoverable signal that needs
//                         the customer's attention (overdue task,
//                         maintenance window, etc.)
//   not_reporting       — telemetry was previously received and has
//                         stopped, OR a critical incident is open.
//                         Amber, not red: absence of telemetry alone
//                         is NOT a confirmed outage — the device may
//                         still be operational on site.
//   integration_pending — explicit "awaiting carrier/API integration"
//                         (reserved; not auto-derived in this layer —
//                         a future backend signal will set this when
//                         we know an integration is queued)
//
// Red is deliberately NOT used by any of these buckets.  Real
// outages surface through incidents — which have their own rendering
// in the incident feed and incident drawer.
//
// Internal roles (Admin / SuperAdmin / DataSteward / DataEntry) keep
// their existing labels and badges via the existing `statusLabel()` /
// `statusColor()` exports above.  Nothing in this block changes
// their UX.

export const CUSTOMER_STATUS = {
  REPORTING:           "reporting",
  INVENTORY:           "inventory",
  ATTENTION_NEEDED:    "attention_needed",
  NOT_REPORTING:       "not_reporting",
  INTEGRATION_PENDING: "integration_pending",
};

const CUSTOMER_LABELS = {
  reporting:           "Reporting",
  inventory:           "Inventory Record",
  attention_needed:    "Attention Needed",
  not_reporting:       "Not Reporting",
  integration_pending: "API / Carrier Integration Pending",
};

const CUSTOMER_COLORS = {
  reporting: {
    dot: "bg-emerald-500", text: "text-emerald-700",
    bg:  "bg-emerald-50",  border: "border-emerald-200",
  },
  inventory: {
    // Calm slate — explicitly NOT alarming.  An inventory record is
    // a neutral fact about the deployment, not a problem.
    dot: "bg-slate-400", text: "text-slate-700",
    bg:  "bg-slate-50",  border: "border-slate-200",
  },
  attention_needed: {
    dot: "bg-amber-500", text: "text-amber-700",
    bg:  "bg-amber-50",  border: "border-amber-200",
  },
  not_reporting: {
    // Amber, NOT red.  Absence of telemetry is informative, not
    // alarming — the device may still be operational in the field.
    // Genuine outages surface separately through the incident feed.
    dot: "bg-amber-500", text: "text-amber-700",
    bg:  "bg-amber-50",  border: "border-amber-200",
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
 * `critical_incidents` for the inventory-vs-not-reporting split.
 *
 * Disambiguation: the canonical engine groups never-reported sites
 * AND went-dark sites into `offline`.  For customer surfaces we
 * split those: a site that has never checked in AND has no critical
 * incident is treated as `inventory` (a registered location with
 * no telemetry yet), NOT `not_reporting`.  Absence of telemetry on a
 * brand-new location is not a problem — it just means the device
 * hasn't started reporting yet.
 */
export function toCustomerStatus(site) {
  const canonical = toCanonical(site);

  if (canonical === CANONICAL.CONNECTED) {
    return CUSTOMER_STATUS.REPORTING;
  }
  if (canonical === CANONICAL.ATTENTION) {
    return CUSTOMER_STATUS.ATTENTION_NEEDED;
  }
  if (canonical === CANONICAL.OFFLINE) {
    const everCheckedIn = !!site?.last_checkin;
    const hasCriticalIncident = (site?.critical_incidents ?? 0) > 0;
    if (!everCheckedIn && !hasCriticalIncident) {
      return CUSTOMER_STATUS.INVENTORY;
    }
    return CUSTOMER_STATUS.NOT_REPORTING;
  }
  // unknown / null — inventory is the neutral default, never alarming
  return CUSTOMER_STATUS.INVENTORY;
}

/** Display label for a customer-status key. */
export function customerStatusLabel(key) {
  return CUSTOMER_LABELS[key] || CUSTOMER_LABELS.inventory;
}

/** Tailwind color tokens for a customer-status key. */
export function customerStatusColor(key) {
  return CUSTOMER_COLORS[key] || CUSTOMER_COLORS.inventory;
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

/**
 * Aggregate a list of site summaries into the five customer buckets.
 *
 * The canonical `attention.summary` from /command/summary collapses
 * never-reported sites and went-dark sites into one `offline` bucket.
 * Customer surfaces need them separated — a registered location that
 * has never reported is inventory (neutral), not an outage.  This
 * helper does the split client-side from `site_summaries`.
 *
 * Returns ``{ total, reporting, inventory, attention_needed,
 *             not_reporting, integration_pending }``.
 */
export function getCustomerCounts(siteSummaries = []) {
  const counts = {
    total: 0,
    reporting: 0,
    inventory: 0,
    attention_needed: 0,
    not_reporting: 0,
    integration_pending: 0,
  };
  for (const s of siteSummaries) {
    counts.total += 1;
    const key = toCustomerStatus(s);
    if (key in counts) counts[key] += 1;
  }
  return counts;
}
