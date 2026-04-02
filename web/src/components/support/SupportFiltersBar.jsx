import { Search, Filter, X } from "lucide-react";

const STATUS_OPTIONS = [
  { value: "", label: "All Statuses" },
  { value: "active", label: "Active" },
  { value: "resolved", label: "Resolved" },
  { value: "escalated", label: "Escalated" },
];

export default function SupportFiltersBar({ filters, onChange }) {
  const set = (key) => (e) => onChange({ ...filters, [key]: e.target.value });

  const hasFilters = filters.status || filters.escalated || filters.search;

  return (
    <div className="px-3 py-2.5 border-b border-gray-200 space-y-2">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
        <input
          type="text"
          value={filters.search || ""}
          onChange={set("search")}
          placeholder="Search sessions..."
          className="w-full pl-8 pr-3 py-1.5 text-xs border border-gray-200 rounded-lg bg-gray-50 focus:outline-none focus:ring-1 focus:ring-red-500 focus:bg-white"
        />
      </div>

      {/* Filter row */}
      <div className="flex items-center gap-2">
        <Filter className="w-3 h-3 text-gray-400 flex-shrink-0" />
        <select
          value={filters.status || ""}
          onChange={set("status")}
          className="flex-1 text-xs border border-gray-200 rounded-md px-2 py-1 bg-white focus:outline-none focus:ring-1 focus:ring-red-500"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <label className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer whitespace-nowrap">
          <input
            type="checkbox"
            checked={filters.escalated === "true"}
            onChange={(e) => onChange({ ...filters, escalated: e.target.checked ? "true" : "" })}
            className="accent-red-600 w-3 h-3"
          />
          Escalated
        </label>

        {hasFilters && (
          <button
            onClick={() => onChange({ status: "", escalated: "", search: "" })}
            className="text-gray-400 hover:text-gray-600"
            title="Clear filters"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
