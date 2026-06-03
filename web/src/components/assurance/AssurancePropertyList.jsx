import { sortPropertiesByUrgency } from "@/lib/assuranceStatus";
import AssuranceBadge from "@/components/assurance/AssuranceBadge";

/**
 * Property list with an Assurance column. Rows are sorted by urgency
 * (Critical, then Attention Needed, then the rest). Selecting a row calls
 * onSelect(site_id) so the parent can show the detail panel.
 */
export default function AssurancePropertyList({ rows, selectedId, onSelect }) {
  const sorted = sortPropertiesByUrgency(rows);

  if (!sorted.length) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 px-5 py-10 text-center text-sm text-gray-400">
        No properties to show.
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-gray-500 border-b border-gray-100">
            <th className="px-4 py-3 font-medium">Property</th>
            <th className="px-4 py-3 font-medium">Assurance</th>
            <th className="px-4 py-3 font-medium hidden md:table-cell">Top item</th>
            <th className="px-4 py-3 font-medium hidden lg:table-cell">Last evaluated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {sorted.map((row) => {
            const topReason = row.reasons && row.reasons.length ? (row.reasons[0].message || row.reasons[0].code) : (row.error === "unavailable" ? "Assurance not enabled" : "—");
            return (
              <tr
                key={row.site_id}
                onClick={() => onSelect && onSelect(row.site_id)}
                className={`cursor-pointer hover:bg-gray-50 ${selectedId === row.site_id ? "bg-gray-50" : ""}`}
              >
                <td className="px-4 py-3">
                  <div className="font-medium text-gray-800">{row.site_name}</div>
                  <div className="text-xs text-gray-400">{row.site_id}</div>
                </td>
                <td className="px-4 py-3"><AssuranceBadge label={row.assurance_label} /></td>
                <td className="px-4 py-3 text-gray-600 hidden md:table-cell">{topReason}</td>
                <td className="px-4 py-3 text-gray-400 text-xs hidden lg:table-cell">
                  {row.as_of ? new Date(row.as_of).toLocaleString() : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
