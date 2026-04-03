import { Search, Filter, X } from "lucide-react";

const STATUS_OPTIONS = [
  { value: "", label: "All Statuses" },
  { value: "succeeded", label: "Succeeded" },
  { value: "failed", label: "Failed" },
  { value: "blocked", label: "Blocked" },
  { value: "cooldown", label: "Cooldown" },
  { value: "running", label: "Running" },
];

const VERIFICATION_OPTIONS = [
  { value: "", label: "All Verification" },
  { value: "passed", label: "Passed" },
  { value: "failed", label: "Failed" },
  { value: "skipped", label: "Skipped" },
];

const ACTION_TYPES = [
  { value: "", label: "All Actions" },
  { value: "refresh_diagnostics", label: "Refresh Diagnostics" },
  { value: "refresh_device_status", label: "Refresh Device" },
  { value: "refresh_telemetry", label: "Refresh Telemetry" },
  { value: "retry_voice_check", label: "Retry Voice" },
  { value: "retry_connectivity_check", label: "Retry Connectivity" },
  { value: "retry_zoho_sync", label: "Retry Zoho Sync" },
  { value: "recheck_after_delay", label: "Delayed Recheck" },
  { value: "check_backup_path", label: "Check Backup Path" },
];

export default function RemediationFiltersBar({ filters, onChange }) {
  const set = (key) => (e) => onChange({ ...filters, [key]: e.target.value });
  const toggle = (key) => () => onChange({ ...filters, [key]: !filters[key] });

  const hasFilters = Object.entries(filters).some(([k, v]) => k !== "search" && v);

  return (
    <div className="bg-white border border-gray-200 rounded-lg px-3 py-2.5 space-y-2">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
        <input
          type="text"
          value={filters.search || ""}
          onChange={set("search")}
          placeholder="Search site, device, ticket, session..."
          className="w-full pl-8 pr-3 py-1.5 text-xs border border-gray-200 rounded-lg bg-gray-50 focus:outline-none focus:ring-1 focus:ring-red-500 focus:bg-white"
        />
      </div>

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-2">
        <Filter className="w-3 h-3 text-gray-400 flex-shrink-0" />

        <select value={filters.status || ""} onChange={set("status")}
          className="text-xs border border-gray-200 rounded-md px-2 py-1 bg-white focus:outline-none focus:ring-1 focus:ring-red-500">
          {STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        <select value={filters.verification_status || ""} onChange={set("verification_status")}
          className="text-xs border border-gray-200 rounded-md px-2 py-1 bg-white focus:outline-none focus:ring-1 focus:ring-red-500">
          {VERIFICATION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        <select value={filters.action_type || ""} onChange={set("action_type")}
          className="text-xs border border-gray-200 rounded-md px-2 py-1 bg-white focus:outline-none focus:ring-1 focus:ring-red-500">
          {ACTION_TYPES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        <label className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer whitespace-nowrap">
          <input type="checkbox" checked={!!filters.escalated_only} onChange={toggle("escalated_only")} className="accent-red-600 w-3 h-3" />
          Escalated
        </label>

        <label className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer whitespace-nowrap">
          <input type="checkbox" checked={!!filters.blocked_only} onChange={toggle("blocked_only")} className="accent-amber-600 w-3 h-3" />
          Blocked
        </label>

        {hasFilters && (
          <button onClick={() => onChange({ search: filters.search || "" })} className="text-gray-400 hover:text-gray-600" title="Clear filters">
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
