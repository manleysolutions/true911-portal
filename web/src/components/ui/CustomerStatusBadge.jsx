import { customerSitePresentation } from "@/lib/attention";

/**
 * Customer-facing site status badge.
 *
 * Renders one of five calm, enterprise-grade buckets:
 *   Operational | Monitoring Pending | Attention Needed |
 *   Confirmed Offline | Integration Pending
 *
 * For internal/operations roles (Admin, SuperAdmin, DataSteward,
 * DataEntry) this returns `null` — the caller should fall back to
 * the raw StatusBadge so admin workflows are not degraded.
 *
 * Props:
 *   site  — any object with canonical_status OR a legacy `status`
 *           plus optional `last_checkin` and `critical_incidents`.
 *   role  — the current user's role string.
 *   size  — "sm" (default) | "md"
 */
export default function CustomerStatusBadge({ site, role, size = "sm" }) {
  const pres = customerSitePresentation(site, role);
  if (!pres) return null;
  const padding = size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${pres.bg} ${pres.text} ${pres.border} ${padding}`}
      title={pres.label}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${pres.dot} flex-shrink-0`} />
      {pres.label}
    </span>
  );
}
