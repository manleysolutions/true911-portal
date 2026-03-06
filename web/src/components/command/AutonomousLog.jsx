import { useState, useEffect } from "react";
import { Bot, Loader2, Zap, Shield, Wrench, ArrowUpCircle, CheckCircle2, Calendar } from "lucide-react";
import { apiFetch } from "@/api/client";

const TYPE_ICONS = {
  incident_created: { icon: Zap, color: "text-red-500", bg: "bg-red-50" },
  diagnostic_executed: { icon: Wrench, color: "text-blue-500", bg: "bg-blue-50" },
  incident_routed: { icon: ArrowUpCircle, color: "text-indigo-500", bg: "bg-indigo-50" },
  self_heal_device_reboot: { icon: Shield, color: "text-emerald-500", bg: "bg-emerald-50" },
  self_heal_connection_reset: { icon: Shield, color: "text-emerald-500", bg: "bg-emerald-50" },
  escalations_processed: { icon: ArrowUpCircle, color: "text-amber-500", bg: "bg-amber-50" },
  verifications_scheduled: { icon: Calendar, color: "text-purple-500", bg: "bg-purple-50" },
  problem_verified: { icon: CheckCircle2, color: "text-orange-500", bg: "bg-orange-50" },
  rule_fired: { icon: Zap, color: "text-yellow-500", bg: "bg-yellow-50" },
  readiness_recalculated: { icon: CheckCircle2, color: "text-gray-500", bg: "bg-gray-50" },
};

export default function AutonomousLog({ siteId, limit = 20 }) {
  const [actions, setActions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let url = `/command/autonomous/actions?limit=${limit}`;
    if (siteId) url += `&site_id=${siteId}`;
    apiFetch(url)
      .then(setActions)
      .catch(() => setActions([]))
      .finally(() => setLoading(false));
  }, [siteId, limit]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-2">
        <Bot className="w-4 h-4 text-indigo-600" />
        <h3 className="text-sm font-semibold text-gray-900">Autonomous Actions</h3>
        <span className="text-[10px] text-gray-400 ml-auto">{actions.length} recent</span>
      </div>

      {actions.length === 0 ? (
        <p className="text-xs text-gray-500 text-center py-4">No autonomous actions recorded.</p>
      ) : (
        <div className="space-y-1.5 max-h-[400px] overflow-y-auto">
          {actions.map(action => {
            const typeConfig = TYPE_ICONS[action.action_type] || TYPE_ICONS.rule_fired;
            const Icon = typeConfig.icon;
            return (
              <div key={action.id} className="flex items-start gap-2 p-2.5 bg-gray-50 rounded-lg">
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${typeConfig.bg}`}>
                  <Icon className={`w-3.5 h-3.5 ${typeConfig.color}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-gray-900">{action.summary}</div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[10px] text-gray-500">{action.action_type.replace(/_/g, " ")}</span>
                    <span className="text-[10px] text-gray-400">
                      {new Date(action.created_at).toLocaleString()}
                    </span>
                    {action.result && (
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${
                        action.result === "resolved" ? "bg-emerald-100 text-emerald-700" :
                        action.result === "pass" ? "bg-blue-100 text-blue-700" :
                        "bg-gray-100 text-gray-600"
                      }`}>{action.result}</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
