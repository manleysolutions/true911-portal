import { DeviceHealthBadge, StatusBadge } from "./RecoveryStatusBadge";
import { formatDistanceToNow } from "./utils";

/**
 * Device-centric recovery view.
 * Aggregates remediation records by device and shows health status.
 */
export default function DeviceRecoveryTable({ records }) {
  if (!records || records.length === 0) {
    return (
      <div className="text-center py-8 text-sm text-gray-400">
        No device remediation data available.
      </div>
    );
  }

  // Aggregate by device
  const deviceMap = {};
  const sevenDaysAgo = new Date();
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

  records.forEach((r) => {
    const key = r.device_id || `site-${r.site_id || "none"}`;
    if (!deviceMap[key]) {
      deviceMap[key] = {
        device_id: r.device_id,
        site_id: r.site_id,
        tenant_id: r.tenant_id,
        total: 0,
        succeeded: 0,
        failed_verification: 0,
        blocked: 0,
        has_escalation: false,
        last_action: null,
        last_status: null,
        records_7d: 0,
      };
    }
    const d = deviceMap[key];
    if (new Date(r.created_at) >= sevenDaysAgo) {
      d.records_7d++;
    }
    d.total++;
    if (r.status === "succeeded") d.succeeded++;
    if (r.verification_status === "failed") d.failed_verification++;
    if (r.status === "blocked" || r.status === "cooldown") d.blocked++;
    if (r.escalation_id) d.has_escalation = true;
    if (!d.last_action || new Date(r.created_at) > new Date(d.last_action)) {
      d.last_action = r.created_at;
      d.last_status = r.status;
    }
  });

  const devices = Object.values(deviceMap).sort((a, b) => {
    // Sort noisy/problematic devices first
    const scoreA = a.failed_verification * 3 + (a.has_escalation ? 5 : 0) + (a.total - a.succeeded);
    const scoreB = b.failed_verification * 3 + (b.has_escalation ? 5 : 0) + (b.total - b.succeeded);
    return scoreB - scoreA;
  });

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-200 text-gray-500 text-[10px] uppercase tracking-wider">
            <th className="text-left py-2 px-2 font-semibold">Device</th>
            <th className="text-left py-2 px-2 font-semibold">Site</th>
            <th className="text-left py-2 px-2 font-semibold">Tenant</th>
            <th className="text-center py-2 px-2 font-semibold">7d Total</th>
            <th className="text-center py-2 px-2 font-semibold">Success Rate</th>
            <th className="text-center py-2 px-2 font-semibold">Failed Verif.</th>
            <th className="text-left py-2 px-2 font-semibold">Last Result</th>
            <th className="text-left py-2 px-2 font-semibold">Last Action</th>
            <th className="text-left py-2 px-2 font-semibold">Health</th>
          </tr>
        </thead>
        <tbody>
          {devices.map((d, i) => {
            const successRate = d.total > 0 ? Math.round((d.succeeded / d.total) * 100) : 0;
            const health = computeHealth(d);

            return (
              <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                <td className="py-2 px-2 font-medium text-gray-700">{d.device_id ?? "—"}</td>
                <td className="py-2 px-2 text-gray-600">{d.site_id ?? "—"}</td>
                <td className="py-2 px-2 text-gray-600 truncate max-w-[80px]">{d.tenant_id}</td>
                <td className="py-2 px-2 text-center text-gray-700">{d.records_7d}</td>
                <td className="py-2 px-2 text-center">
                  <span className={`font-medium ${successRate >= 80 ? "text-green-600" : successRate >= 50 ? "text-amber-600" : "text-red-600"}`}>
                    {successRate}%
                  </span>
                </td>
                <td className="py-2 px-2 text-center">
                  <span className={d.failed_verification > 0 ? "text-red-600 font-medium" : "text-gray-400"}>
                    {d.failed_verification}
                  </span>
                </td>
                <td className="py-2 px-2">{d.last_status ? <StatusBadge status={d.last_status} /> : "—"}</td>
                <td className="py-2 px-2 text-gray-500">{formatDistanceToNow(d.last_action)}</td>
                <td className="py-2 px-2"><DeviceHealthBadge label={health} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function computeHealth(d) {
  if (d.has_escalation && d.failed_verification > 0) return "Manual Review Needed";
  if (d.has_escalation) return "Escalated";
  if (d.failed_verification >= 3) return "Repeated Failures";
  if (d.blocked >= 3) return "Cooldown Heavy";
  if (d.total > 0 && d.succeeded < d.total && d.last_status !== "succeeded") return "Recovering";
  return "Stable";
}
