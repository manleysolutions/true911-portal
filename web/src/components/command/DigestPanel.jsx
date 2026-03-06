import { useState, useEffect } from "react";
import { FileBarChart, Loader2, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { apiFetch } from "@/api/client";

function TrendIcon({ trend }) {
  if (trend === "increasing") return <TrendingUp className="w-3 h-3 text-red-500" />;
  if (trend === "decreasing") return <TrendingDown className="w-3 h-3 text-emerald-500" />;
  return <Minus className="w-3 h-3 text-gray-400" />;
}

function StatRow({ label, value, sub }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-xs text-gray-600">{label}</span>
      <div className="text-right">
        <span className="text-sm font-bold text-gray-900">{value}</span>
        {sub && <span className="text-[10px] text-gray-400 ml-1">{sub}</span>}
      </div>
    </div>
  );
}

export default function DigestPanel() {
  const [digests, setDigests] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch("/command/digests?limit=5")
      .then(setDigests)
      .catch(() => setDigests([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
      </div>
    );
  }

  if (digests.length === 0) {
    return (
      <div className="text-center py-4">
        <p className="text-xs text-gray-500">No operational digests generated yet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <FileBarChart className="w-4 h-4 text-teal-600" />
        <h3 className="text-sm font-semibold text-gray-900">Operational Digests</h3>
      </div>

      {digests.map(digest => {
        let data = {};
        try { data = JSON.parse(digest.summary_json); } catch {}
        const isWeekly = digest.digest_type === "weekly";

        return (
          <div key={digest.id} className="bg-gray-50 rounded-xl p-4 border border-gray-100">
            <div className="flex items-center justify-between mb-3">
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                isWeekly ? "bg-teal-100 text-teal-700" : "bg-blue-100 text-blue-700"
              }`}>{digest.digest_type}</span>
              <span className="text-[10px] text-gray-400">
                {new Date(digest.period_end).toLocaleDateString()}
              </span>
            </div>

            {isWeekly && data.incidents ? (
              <div className="space-y-0.5 divide-y divide-gray-100">
                <div className="flex items-center justify-between py-1.5">
                  <span className="text-xs text-gray-600">Incidents</span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-bold text-gray-900">
                      {data.incidents.opened} opened / {data.incidents.resolved} resolved
                    </span>
                    <TrendIcon trend={data.incidents.trend} />
                  </div>
                </div>
                <StatRow label="Device Health" value={`${data.devices?.health_pct || 0}%`}
                  sub={`${data.devices?.active || 0}/${data.devices?.total || 0}`} />
                <StatRow label="Verifications Completed" value={data.verifications?.completed || 0}
                  sub={`${data.verifications?.pending || 0} pending`} />
                <StatRow label="Autonomous Actions" value={data.autonomous_ops?.total_actions || 0}
                  sub={`${data.autonomous_ops?.self_heals_resolved || 0} self-healed`} />
              </div>
            ) : (
              <div className="space-y-0.5 divide-y divide-gray-100">
                <StatRow label="Sites Needing Attention" value={data.sites_needing_attention || 0}
                  sub={`of ${data.sites_total || 0}`} />
                <StatRow label="Devices Offline" value={data.devices_offline || 0}
                  sub={`of ${data.devices_total || 0}`} />
                <StatRow label="Tasks Overdue" value={data.verification_tasks_overdue || 0}
                  sub={`${data.verification_tasks_due || 0} due`} />
                <StatRow label="Incidents" value={`${data.incidents_opened || 0} / ${data.incidents_resolved || 0}`}
                  sub="opened / resolved" />
                <StatRow label="Auto Actions" value={data.autonomous_actions || 0} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
