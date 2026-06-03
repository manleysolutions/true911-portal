/**
 * Pure presentation + aggregation helpers for Assurance labels.
 *
 * The Assurance Engine (backend) owns the label, reasons, and recommended
 * action — this module ONLY maps a label string to display metadata
 * (colours / order) and aggregates counts for the dashboard. No business
 * logic, no React, no I/O → trivially testable.
 */

// Canonical label strings returned by GET /api/assurance/site/{id}.
export const ASSURANCE_META = {
  "Protected": {
    key: "protected", group: "protected", order: 2, label: "Protected",
    badge: "bg-green-50 text-green-700 border-green-200", dot: "bg-green-500",
    card: "bg-green-50 border-green-200 text-green-700",
  },
  "Attention Needed": {
    key: "attention", group: "attention", order: 1, label: "Attention Needed",
    badge: "bg-amber-50 text-amber-700 border-amber-200", dot: "bg-amber-500",
    card: "bg-amber-50 border-amber-200 text-amber-700",
  },
  "Critical": {
    key: "critical", group: "critical", order: 0, label: "Critical",
    badge: "bg-red-50 text-red-700 border-red-200", dot: "bg-red-500",
    card: "bg-red-50 border-red-200 text-red-700",
  },
  "Pending Install": {
    key: "pending", group: "pending", order: 3, label: "Pending Install",
    badge: "bg-blue-50 text-blue-700 border-blue-200", dot: "bg-blue-500",
    card: "bg-blue-50 border-blue-200 text-blue-700",
  },
  "Inactive / Deactivated": {
    key: "inactive", group: "inactive", order: 5, label: "Inactive / Deactivated",
    badge: "bg-gray-100 text-gray-600 border-gray-200", dot: "bg-gray-400",
    card: "bg-gray-50 border-gray-200 text-gray-600",
  },
  "Unknown": {
    key: "unknown", group: "unknown", order: 4, label: "Unknown",
    badge: "bg-gray-50 text-gray-500 border-gray-200", dot: "bg-gray-300",
    card: "bg-gray-50 border-gray-200 text-gray-500",
  },
};

export const UNKNOWN_META = ASSURANCE_META["Unknown"];

/** Display metadata for a label; falls back to Unknown for anything unexpected. */
export function metaForLabel(label) {
  return ASSURANCE_META[label] || UNKNOWN_META;
}

/**
 * Sort property rows by urgency: Critical first, then Attention Needed, then
 * the rest by order, then alphabetically by name. Does not mutate the input.
 */
export function sortPropertiesByUrgency(rows) {
  return [...(rows || [])].sort((a, b) => {
    const oa = metaForLabel(a.assurance_label).order;
    const ob = metaForLabel(b.assurance_label).order;
    if (oa !== ob) return oa - ob;
    const na = String(a.site_name || a.site_id || "");
    const nb = String(b.site_name || b.site_id || "");
    return na.localeCompare(nb);
  });
}

/** Count rows by group for the summary cards / executive widget. */
export function summarizePortfolio(items) {
  const counts = {
    protected: 0, attention: 0, critical: 0, pending: 0,
    inactive: 0, unknown: 0, total: 0,
  };
  for (const it of items || []) {
    const group = metaForLabel(it.assurance_label).group;
    if (counts[group] === undefined) counts.unknown += 1;
    else counts[group] += 1;
    counts.total += 1;
  }
  return counts;
}
