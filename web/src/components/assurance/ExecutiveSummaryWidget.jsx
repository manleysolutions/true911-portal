import { ShieldCheck } from "lucide-react";

/**
 * Compact "Protected Locations" executive summary widget.
 *
 *   Protected: 1
 *   Attention Needed: 0
 *   Critical: 0
 *   Pending Install: 3
 */
const ROWS = [
  { key: "protected", label: "Protected", dot: "bg-green-500", val: "text-green-700" },
  { key: "attention", label: "Attention Needed", dot: "bg-amber-500", val: "text-amber-700" },
  { key: "critical", label: "Critical", dot: "bg-red-500", val: "text-red-700" },
  { key: "pending", label: "Pending Install", dot: "bg-blue-500", val: "text-blue-700" },
];

export default function ExecutiveSummaryWidget({ counts }) {
  const c = counts || {};
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 mb-3">
        <ShieldCheck className="w-4 h-4 text-green-600" />
        <h3 className="text-sm font-semibold text-gray-800">Protected Locations</h3>
      </div>
      <ul className="space-y-2">
        {ROWS.map((r) => (
          <li key={r.key} className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 text-gray-600">
              <span className={`w-1.5 h-1.5 rounded-full ${r.dot}`} />
              {r.label}
            </span>
            <span className={`font-semibold tabular-nums ${r.val}`}>{c[r.key] ?? 0}</span>
          </li>
        ))}
      </ul>
      <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
        <span>Total locations</span>
        <span className="font-medium tabular-nums">{c.total ?? 0}</span>
      </div>
    </div>
  );
}
