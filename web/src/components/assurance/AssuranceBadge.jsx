import { metaForLabel } from "@/lib/assuranceStatus";

/**
 * Customer-facing assurance label badge.
 * Protected (green) · Attention Needed (yellow) · Critical (red) ·
 * Pending Install (blue) · Inactive (gray) · Unknown (gray).
 *
 * The label string comes straight from the Assurance API — this only renders it.
 */
export default function AssuranceBadge({ label, size = "sm" }) {
  const m = metaForLabel(label);
  const padding = size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${m.badge} ${padding}`}
      title={m.label}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${m.dot} flex-shrink-0`} />
      {m.label}
    </span>
  );
}
