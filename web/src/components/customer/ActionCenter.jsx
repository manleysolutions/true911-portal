import { useState, useEffect, useCallback } from "react";
import { ClipboardCheck, ShieldCheck, Users, Repeat, AlertOctagon, AlertTriangle, History, ChevronRight, MessageSquare } from "lucide-react";
import { apiFetch } from "@/api/client";
import { actionCenterHeadline } from "@/components/customer/selfService";

// ════════════════════════════════════════════════════════════════════
// ActionCenter — "What do I need to do?" for the whole portfolio.
//
// GET /customer/action-center (self-service, flag-gated).  A 404 means the
// console is off for this user: the component renders nothing and the
// dashboard is exactly what it was.  Every item opens the location workspace.
// ════════════════════════════════════════════════════════════════════

function Bucket({ icon: Icon, title, items, tone, render, onOpen }) {
  if (!items?.length) return null;
  const toneCls = { amber: "text-amber-700", red: "text-red-700", blue: "text-blue-700", slate: "text-slate-700" }[tone];
  return (
    <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
      <div className="px-3.5 py-2.5 border-b border-slate-100 flex items-center gap-2">
        <Icon className={`w-3.5 h-3.5 ${toneCls}`} />
        <p className="text-[12px] font-semibold text-slate-800 flex-1">{title}</p>
        <span className={`text-[12px] font-semibold tabular-nums ${toneCls}`}>{items.length}</span>
      </div>
      <div className="divide-y divide-slate-100 max-h-48 overflow-y-auto">
        {items.slice(0, 20).map((it, i) => (
          <button key={i} type="button" disabled={!it.location_ref} onClick={() => onOpen({ ref: it.location_ref, name: it.location })}
            className="w-full text-left px-3.5 py-2 hover:bg-slate-50 flex items-center gap-2">
            <span className="text-[12px] text-slate-800 flex-1 min-w-0 truncate">{render(it)}</span>
            <ChevronRight className="w-3.5 h-3.5 text-slate-300 flex-shrink-0" />
          </button>
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

  const c = data.counts || {};
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="px-5 py-3.5 border-b border-slate-100 flex items-center gap-2">
        <ClipboardCheck className="w-4 h-4 text-slate-700" />
        <div className="flex-1">
          <h2 className="text-[13px] font-semibold text-slate-900">What needs your attention</h2>
          <p className="text-[11.5px] text-slate-500">{actionCenterHeadline(c)}</p>
        </div>
      </div>
      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
        <Bucket icon={MessageSquare} title="Waiting on you" tone="amber" items={data.awaiting_your_response} onOpen={onOpenLocation}
          render={(it) => `${it.location} — ${it.request_label}`} />
        <Bucket icon={AlertTriangle} title="Needs attention" tone="red" items={data.needs_attention} onOpen={onOpenLocation}
          render={(it) => `${it.location} — ${it.status}`} />
        <Bucket icon={ShieldCheck} title="E911 verification required" tone="amber" items={data.e911_verification_required} onOpen={onOpenLocation}
          render={(it) => `${it.location} — ${it.label}`} />
        <Bucket icon={Users} title="Missing contact information" tone="amber" items={data.missing_contact_information} onOpen={onOpenLocation}
          render={(it) => it.location} />
        <Bucket icon={Repeat} title="Service change requests" tone="blue" items={data.service_change_requests} onOpen={onOpenLocation}
          render={(it) => `${it.location} — ${it.request_label}: ${it.status_label}`} />
        <Bucket icon={AlertOctagon} title="Open problems" tone="blue" items={data.open_problems} onOpen={onOpenLocation}
          render={(it) => `${it.location} — ${it.status_label}`} />
        <Bucket icon={History} title="Recently updated" tone="slate" items={data.recently_updated} onOpen={() => {}}
          render={(it) => `${it.by} · ${it.summary}`} />
      </div>
    </div>
  );
}
