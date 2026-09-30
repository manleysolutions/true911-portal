import { useState, useEffect, useCallback } from "react";
import { ClipboardCheck, ShieldCheck, Users, Repeat, AlertOctagon, AlertTriangle, History, ChevronRight, MessageSquare, Hourglass } from "lucide-react";
import { apiFetch } from "@/api/client";
import { actionCenterHeadline, actionCenterSections } from "@/components/customer/selfService";

// ════════════════════════════════════════════════════════════════════
// ActionCenter — "What do I need to do?" for the whole portfolio.
//
// GET /customer/action-center (self-service, flag-gated).  A 404 means the
// console is off for this user: the component renders nothing and the
// dashboard is exactly what it was.  Actionable buckets carry a button that
// opens the location straight into the task (e.g. Verify E911); informational
// buckets (records being prepared, requests in progress) never ask the
// customer to do something they cannot do.
// ════════════════════════════════════════════════════════════════════

const ICONS = {
  awaiting_your_response: MessageSquare, needs_attention: AlertTriangle,
  e911_confirmation_required: ShieldCheck, missing_contact_information: Users,
  service_change_requests: Repeat, open_problems: AlertOctagon, e911_not_ready: Hourglass,
  recently_updated: History,
};
const TONE = { amber: "text-amber-700", red: "text-red-700", blue: "text-blue-700", slate: "text-slate-600" };

function Bucket({ section, onOpen }) {
  const { key, title, subtitle, items, tone, row, action, noOpen } = section;
  if (!items.length) return null;
  const Icon = ICONS[key] || ClipboardCheck;
  return (
    <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
      <div className="px-3.5 py-2.5 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <Icon className={`w-3.5 h-3.5 ${TONE[tone]}`} />
          <p className="text-[12px] font-semibold text-slate-800 flex-1">{title}</p>
          <span className={`text-[12px] font-semibold tabular-nums ${TONE[tone]}`}>{items.length}</span>
        </div>
        {subtitle && <p className="text-[10.5px] text-slate-400 mt-0.5">{subtitle}</p>}
      </div>
      <div className="divide-y divide-slate-100 max-h-48 overflow-y-auto">
        {items.slice(0, 20).map((it, i) => (
          noOpen || !it.location_ref ? (
            <div key={i} className="px-3.5 py-2 text-[12px] text-slate-700 truncate">{row(it)}</div>
          ) : (
            <button key={i} type="button"
              onClick={() => onOpen({ ref: it.location_ref, name: it.location, intent: action?.intent || null })}
              className="w-full text-left px-3.5 py-2 hover:bg-slate-50 flex items-center gap-2">
              <span className="text-[12px] text-slate-800 flex-1 min-w-0 truncate">{row(it)}</span>
              {action && <span className="text-[11px] font-medium text-slate-700 border border-slate-200 rounded px-1.5 py-0.5 flex-shrink-0">{action.label}</span>}
              <ChevronRight className="w-3.5 h-3.5 text-slate-300 flex-shrink-0" />
            </button>
          )
        ))}
      </div>
    </div>
  );
}

export default function ActionCenter({ onOpenLocation, refreshKey }) {
  const [data, setData] = useState(null);
  const load = useCallback(async () => {
    try { setData((await apiFetch("/customer/action-center")).data); }
    catch { setData(null); }
  }, []);
  useEffect(() => { load(); }, [load, refreshKey]);
  if (!data) return null;

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="px-5 py-3.5 border-b border-slate-100 flex items-center gap-2">
        <ClipboardCheck className="w-4 h-4 text-slate-700" />
        <div className="flex-1">
          <h2 className="text-[13px] font-semibold text-slate-900">What needs your attention</h2>
          <p className="text-[11.5px] text-slate-500">{actionCenterHeadline({
            ...data.counts, awaiting_your_response: (data.awaiting_your_response || []).length })}</p>
        </div>
      </div>
      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
        {actionCenterSections(data).map((s) => <Bucket key={s.key} section={s} onOpen={onOpenLocation} />)}
      </div>
    </div>
  );
}
