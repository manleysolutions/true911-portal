import { X, Clock, Building2 } from "lucide-react";
import StatusBadge from "../ui/StatusBadge";
import ComputedStatusBadge from "../ui/ComputedStatusBadge";
import { isDemo } from "@/config";

function timeSince(iso) {
  if (!iso) return "Unknown";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function DrawerHeader({ site, lastActionResult, onClose }) {
  return (
    <div className="flex-shrink-0 border-b border-gray-100">
      <div className="flex items-start justify-between px-5 pt-4 pb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-[10px] text-gray-400 font-mono bg-gray-50 px-1.5 py-0.5 rounded">{site.site_id}</span>
            <StatusBadge status={site.status} />
            {site.computed_status && <ComputedStatusBadge status={site.computed_status} />}
            {site.tenant_id && (
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 border border-blue-100 font-medium">
                {isDemo && site.tenant_id === "demo" ? "Demo Tenant" : site.tenant_id}
              </span>
            )}
          </div>
          <h2 className="font-bold text-gray-900 text-base leading-tight truncate">{site.site_name}</h2>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className="text-xs text-gray-500">{site.customer_name}</span>
            {site.e911_city && (
              <>
                <span className="text-gray-300">·</span>
                <span className="text-xs text-gray-500">{site.e911_city}, {site.e911_state}</span>
              </>
            )}
          </div>
        </div>
        <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 flex-shrink-0 ml-3 mt-0.5">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Last check-in bar */}
      <div className="px-5 pb-3 flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <Clock className="w-3 h-3 text-gray-400" />
          Last check-in: <span className="font-semibold text-gray-700">{timeSince(site.last_checkin)}</span>
        </div>
        {lastActionResult && (
          <div className={`flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full border font-medium ${
            lastActionResult.success
              ? "bg-emerald-50 text-emerald-700 border-emerald-100"
              : "bg-red-50 text-red-700 border-red-100"
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${lastActionResult.success ? "bg-emerald-500" : "bg-red-500"}`} />
            Last action: {lastActionResult.label} — {lastActionResult.success ? "OK" : "Failed"}
          </div>
        )}
      </div>
    </div>
  );
}