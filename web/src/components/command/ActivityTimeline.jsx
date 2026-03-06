import { Clock, AlertOctagon, Eye, Play, CheckCircle2, XCircle, UserCheck, RefreshCw, Activity } from "lucide-react";

const TYPE_CONFIG = {
  incident_created:       { icon: AlertOctagon, color: "text-red-400", dot: "bg-red-500" },
  incident_acknowledged:  { icon: Eye, color: "text-amber-400", dot: "bg-amber-500" },
  incident_in_progress:   { icon: Play, color: "text-blue-400", dot: "bg-blue-500" },
  incident_resolved:      { icon: CheckCircle2, color: "text-emerald-400", dot: "bg-emerald-500" },
  incident_dismissed:     { icon: XCircle, color: "text-slate-400", dot: "bg-slate-500" },
  incident_assigned:      { icon: UserCheck, color: "text-blue-400", dot: "bg-blue-500" },
  readiness_recalculated: { icon: RefreshCw, color: "text-purple-400", dot: "bg-purple-500" },
  verification_scheduled: { icon: Clock, color: "text-cyan-400", dot: "bg-cyan-500" },
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

export default function ActivityTimeline({ activities = [], maxItems = 15 }) {
  const items = activities.slice(0, maxItems);

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-slate-700/50">
        <Activity className="w-4 h-4 text-slate-500" />
        <h3 className="text-sm font-semibold text-white">Activity Timeline</h3>
        <span className="text-xs text-slate-600 ml-auto">{items.length} events</span>
      </div>

      <div className="p-5 max-h-[400px] overflow-y-auto">
        {items.length === 0 ? (
          <p className="text-sm text-slate-600 text-center py-6">No recent activity</p>
        ) : (
          <div className="space-y-0">
            {items.map((act, i) => {
              const cfg = TYPE_CONFIG[act.activity_type] || { icon: Activity, color: "text-slate-400", dot: "bg-slate-500" };
              const Icon = cfg.icon;
              return (
                <div key={act.id || i} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <div className={`w-2.5 h-2.5 rounded-full ${cfg.dot} flex-shrink-0 mt-1.5`} />
                    {i < items.length - 1 && (
                      <div className="w-px flex-1 bg-slate-800 my-1" />
                    )}
                  </div>
                  <div className="flex-1 pb-3.5">
                    <div className="flex items-center gap-2 mb-0.5">
                      <Icon className={`w-3.5 h-3.5 ${cfg.color} flex-shrink-0`} />
                      <span className="text-sm text-slate-300">{act.summary}</span>
                    </div>
                    <div className="flex items-center gap-2 ml-5">
                      {act.actor && act.actor !== "system" && (
                        <span className="text-[10px] text-slate-500">{act.actor}</span>
                      )}
                      {act.site_id && (
                        <span className="text-[10px] text-slate-600">{act.site_id}</span>
                      )}
                      <span className="text-[10px] text-slate-600 ml-auto">{timeSince(act.created_at)}</span>
                    </div>
                    {act.detail && (
                      <p className="text-xs text-slate-600 ml-5 mt-0.5">{act.detail}</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
