import { useState, useEffect } from "react";
import { ActionAudit } from "@/api/entities";
import { CheckCircle, XCircle, Loader2, Clock } from "lucide-react";

function timeSince(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const ACTION_LABELS = {
  PING: "Ping",
  REBOOT: "Reboot CSA",
  GENERATE_REPORT: "Report",
  UPDATE_E911: "Update E911",
  UPDATE_HEARTBEAT: "Update Heartbeat",
  RESTART_CONTAINER: "Restart Container",
  PULL_LOGS: "Pull Logs",
  SWITCH_CHANNEL: "Switch Channel",
  ACK_INCIDENT: "Ack Incident",
  CLOSE_INCIDENT: "Close Incident",
};

export default function ActionTimeline({ site, refreshKey }) {
  const [audits, setAudits] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    ActionAudit.filter({ site_id: site.site_id }, "-timestamp", 10)
      .then(data => { setAudits(data); setLoading(false); });
  }, [site.site_id, refreshKey]);

  return (
    <div className="mb-5">
      <div className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Action Timeline</div>
      {loading ? (
        <div className="flex items-center justify-center py-6">
          <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
        </div>
      ) : audits.length === 0 ? (
        <div className="text-xs text-gray-400 py-3 text-center">No actions recorded for this site yet.</div>
      ) : (
        <div className="space-y-2">
          {audits.map((a, i) => (
            <div key={a.id} className="flex gap-2.5 items-start">
              <div className="flex flex-col items-center pt-0.5">
                {a.result === "success"
                  ? <CheckCircle className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                  : <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                }
                {i < audits.length - 1 && <div className="w-px flex-1 bg-gray-100 my-1 min-h-[10px]" />}
              </div>
              <div className="flex-1 min-w-0 pb-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-semibold text-gray-800">{ACTION_LABELS[a.action_type] || a.action_type}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${a.result === "success" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>
                    {a.result}
                  </span>
                  <span className="text-[10px] text-gray-400 ml-auto flex items-center gap-0.5">
                    <Clock className="w-2.5 h-2.5" />{timeSince(a.timestamp)}
                  </span>
                </div>
                <div className="text-[10px] text-gray-500 mt-0.5">
                  by {a.requester_name || a.user_email?.split("@")[0]}
                  {a.request_id && <span className="ml-1.5 font-mono text-gray-300">{a.request_id.slice(-8)}</span>}
                </div>
                {a.details && <div className="text-[10px] text-gray-500 mt-0.5 leading-relaxed truncate max-w-full" title={a.details}>{a.details}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}