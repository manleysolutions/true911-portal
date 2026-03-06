import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import { ChevronRight, AlertOctagon, ClipboardCheck, WifiOff, Clock } from "lucide-react";

const STATUS_DOT = {
  Connected: "bg-emerald-500",
  "Attention Needed": "bg-amber-500",
  "Not Connected": "bg-red-500",
};

function timeSince(iso) {
  if (!iso) return "--";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function SiteCommandCard({ site }) {
  const {
    site_id, site_name, customer_name, status, kit_type,
    needs_attention, active_incidents = 0, critical_incidents = 0,
    stale_devices = 0, overdue_tasks = 0, pending_tasks = 0,
    total_tasks = 0, vendor_count = 0, last_checkin,
  } = site;

  return (
    <Link
      to={createPageUrl("CommandSite") + `?site=${site_id}`}
      className={`block rounded-xl border p-4 transition-colors hover:bg-slate-800/70 ${
        needs_attention
          ? critical_incidents > 0
            ? "border-red-700/40 bg-red-900/10"
            : "border-amber-700/40 bg-amber-900/10"
          : "border-slate-700/50 bg-slate-900"
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`w-2 h-2 rounded-full ${STATUS_DOT[status] || "bg-slate-500"}`} />
            <p className="text-sm font-medium text-slate-200 truncate">{site_name}</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            {customer_name && <span>{customer_name}</span>}
            {kit_type && <span className="text-slate-600">{kit_type}</span>}
          </div>
        </div>
        <ChevronRight className="w-4 h-4 text-slate-600 flex-shrink-0 mt-0.5" />
      </div>

      {/* Badges row */}
      <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
        {critical_incidents > 0 && (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">
            <AlertOctagon className="w-3 h-3" />
            {critical_incidents} critical
          </span>
        )}
        {active_incidents > 0 && critical_incidents === 0 && (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">
            <AlertOctagon className="w-3 h-3" />
            {active_incidents} active
          </span>
        )}
        {overdue_tasks > 0 && (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">
            <ClipboardCheck className="w-3 h-3" />
            {overdue_tasks} overdue
          </span>
        )}
        {stale_devices > 0 && (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">
            <WifiOff className="w-3 h-3" />
            {stale_devices} stale
          </span>
        )}
        {pending_tasks > 0 && overdue_tasks === 0 && (
          <span className="text-[10px] text-slate-500">
            {pending_tasks}/{total_tasks} tasks pending
          </span>
        )}
        {last_checkin && (
          <span className="text-[10px] text-slate-600 ml-auto flex items-center gap-0.5">
            <Clock className="w-3 h-3" />
            {timeSince(last_checkin)}
          </span>
        )}
      </div>
    </Link>
  );
}
