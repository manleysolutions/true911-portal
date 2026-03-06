import { AlertTriangle, AlertOctagon, Info, Clock, CheckCircle2, UserCheck } from "lucide-react";

const SEV = {
  critical: { bg: "bg-red-900/40", border: "border-red-700/50", text: "text-red-400", icon: AlertOctagon, dot: "bg-red-500" },
  warning:  { bg: "bg-amber-900/30", border: "border-amber-700/40", text: "text-amber-400", icon: AlertTriangle, dot: "bg-amber-500" },
  info:     { bg: "bg-blue-900/30", border: "border-blue-700/40", text: "text-blue-400", icon: Info, dot: "bg-blue-500" },
};

const STATUS_BADGE = {
  open:         { label: "Open", cls: "bg-red-500/20 text-red-400 border-red-500/30" },
  acknowledged: { label: "Acknowledged", cls: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
  closed:       { label: "Closed", cls: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
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

export default function IncidentFeed({ incidents = [], onSelectSite, maxItems = 10 }) {
  const items = incidents.slice(0, maxItems);

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700/50">
        <div className="flex items-center gap-2.5">
          <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
          <h3 className="text-sm font-semibold text-white">Live Incident Feed</h3>
        </div>
        <span className="text-xs text-slate-500">
          {incidents.filter(i => i.status !== "closed").length} active
        </span>
      </div>

      <div className="divide-y divide-slate-800/80 max-h-[420px] overflow-y-auto">
        {items.length === 0 && (
          <div className="px-5 py-10 text-center">
            <CheckCircle2 className="w-8 h-8 text-emerald-500/60 mx-auto mb-2" />
            <p className="text-sm text-slate-500">No active incidents</p>
          </div>
        )}
        {items.map((inc) => {
          const sev = SEV[inc.severity] || SEV.info;
          const sts = STATUS_BADGE[inc.status] || STATUS_BADGE.open;
          const Icon = sev.icon;
          return (
            <div
              key={inc.incident_id || inc.id}
              className="px-5 py-3.5 hover:bg-slate-800/50 transition-colors cursor-pointer"
              onClick={() => onSelectSite?.(inc.site_id)}
            >
              <div className="flex items-start gap-3">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${sev.bg} ${sev.border} border`}>
                  <Icon className={`w-4 h-4 ${sev.text}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide border ${sts.cls}`}>
                      {sts.label}
                    </span>
                    <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase ${sev.text}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${sev.dot}`} />
                      {inc.severity}
                    </span>
                  </div>
                  <p className="text-sm text-slate-200 leading-snug">{inc.summary}</p>
                  <div className="flex items-center gap-3 mt-1.5">
                    <span className="text-xs text-slate-500">{inc.site_name || inc.site_id}</span>
                    <span className="text-slate-700">|</span>
                    <span className="flex items-center gap-1 text-xs text-slate-500">
                      <Clock className="w-3 h-3" />
                      {timeSince(inc.opened_at)}
                    </span>
                    {inc.assigned_to && (
                      <>
                        <span className="text-slate-700">|</span>
                        <span className="flex items-center gap-1 text-xs text-slate-400">
                          <UserCheck className="w-3 h-3" />
                          {inc.assigned_to}
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
