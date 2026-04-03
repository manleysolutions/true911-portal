import { Activity, CheckCircle, XCircle, Clock, ArrowUpRight, AlertTriangle, RefreshCw, Shield } from "lucide-react";

export default function SelfHealingKpiStrip({ records }) {
  const items = records || [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const todayItems = items.filter((r) => new Date(r.created_at) >= today);
  const total = todayItems.length;

  const succeeded = todayItems.filter((r) => r.status === "succeeded").length;
  const successRate = total > 0 ? Math.round((succeeded / total) * 100) : null;

  const failedVerification = todayItems.filter((r) => r.verification_status === "failed").length;
  const blocked = todayItems.filter((r) => r.status === "blocked" || r.status === "cooldown").length;
  const escalated = todayItems.filter((r) => r.escalation_id != null).length;
  const zohoRetries = todayItems.filter((r) => r.action_type === "retry_zoho_sync" && r.status === "succeeded").length;

  // Noisy devices: devices with 3+ remediations today
  const deviceCounts = {};
  todayItems.forEach((r) => { if (r.device_id) deviceCounts[r.device_id] = (deviceCounts[r.device_id] || 0) + 1; });
  const noisyDevices = Object.values(deviceCounts).filter((c) => c >= 3).length;

  // Life-safety: items with issue_category containing life-safety-relevant terms
  const lifeSafety = items.filter((r) =>
    r.status === "failed" && ["device_offline", "voice_quality", "connectivity_warning"].includes(r.issue_category)
  ).length;

  const kpis = [
    { label: "Remediations Today", value: total, icon: Activity, color: "text-blue-600", bg: "bg-blue-50" },
    { label: "Success Rate", value: successRate != null ? `${successRate}%` : "—", icon: CheckCircle, color: "text-green-600", bg: "bg-green-50" },
    { label: "Failed Verifications", value: failedVerification, icon: XCircle, color: failedVerification > 0 ? "text-red-600" : "text-gray-400", bg: failedVerification > 0 ? "bg-red-50" : "bg-gray-50" },
    { label: "Blocked / Cooldown", value: blocked, icon: Clock, color: blocked > 0 ? "text-amber-600" : "text-gray-400", bg: blocked > 0 ? "bg-amber-50" : "bg-gray-50" },
    { label: "Linked Escalations", value: escalated, icon: ArrowUpRight, color: escalated > 0 ? "text-red-600" : "text-gray-400", bg: escalated > 0 ? "bg-red-50" : "bg-gray-50" },
    { label: "Noisy Devices", value: noisyDevices, icon: AlertTriangle, color: noisyDevices > 0 ? "text-orange-600" : "text-gray-400", bg: noisyDevices > 0 ? "bg-orange-50" : "bg-gray-50" },
    { label: "Zoho Sync Recoveries", value: zohoRetries, icon: RefreshCw, color: "text-blue-600", bg: "bg-blue-50" },
    { label: "Life-Safety at Risk", value: lifeSafety, icon: Shield, color: lifeSafety > 0 ? "text-red-600" : "text-green-600", bg: lifeSafety > 0 ? "bg-red-50" : "bg-green-50" },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
      {kpis.map((k) => (
        <div key={k.label} className="bg-white border border-gray-200 rounded-lg px-3 py-2.5">
          <div className="flex items-center gap-1.5 mb-1">
            <div className={`w-6 h-6 ${k.bg} rounded flex items-center justify-center`}>
              <k.icon className={`w-3.5 h-3.5 ${k.color}`} />
            </div>
            <span className="text-lg font-bold text-gray-900">{k.value}</span>
          </div>
          <span className="text-[10px] text-gray-500 leading-tight block">{k.label}</span>
        </div>
      ))}
    </div>
  );
}
