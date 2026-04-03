import { formatDistanceToNow } from "./utils";
import { StatusBadge, VerificationBadge, EscalationLinkedBadge } from "./RecoveryStatusBadge";

const ACTION_LABELS = {
  refresh_diagnostics: "Refresh Diagnostics",
  refresh_device_status: "Refresh Device",
  refresh_telemetry: "Refresh Telemetry",
  retry_voice_check: "Retry Voice",
  retry_connectivity_check: "Retry Connectivity",
  retry_zoho_sync: "Retry Zoho Sync",
  recheck_after_delay: "Delayed Recheck",
  check_backup_path: "Check Backup Path",
  restart_local_monitoring_service: "Restart Monitor",
};

export default function RemediationActivityTable({ records, selectedId, onSelect, loading }) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-40">
        <div className="w-5 h-5 border-2 border-gray-300 border-t-red-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (!records || records.length === 0) {
    return (
      <div className="text-center py-12 text-sm text-gray-400">
        No remediation actions found matching your filters.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-200 text-gray-500 text-[10px] uppercase tracking-wider">
            <th className="text-left py-2 px-2 font-semibold">Time</th>
            <th className="text-left py-2 px-2 font-semibold">Tenant</th>
            <th className="text-left py-2 px-2 font-semibold">Site</th>
            <th className="text-left py-2 px-2 font-semibold">Device</th>
            <th className="text-left py-2 px-2 font-semibold">Issue</th>
            <th className="text-left py-2 px-2 font-semibold">Action</th>
            <th className="text-left py-2 px-2 font-semibold">Status</th>
            <th className="text-left py-2 px-2 font-semibold">Verification</th>
            <th className="text-left py-2 px-2 font-semibold">Esc</th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => {
            const isSelected = r.id === selectedId;
            return (
              <tr
                key={r.id}
                onClick={() => onSelect(r.id)}
                className={`border-b border-gray-100 cursor-pointer transition-colors hover:bg-gray-50 ${
                  isSelected ? "bg-red-50/40" : ""
                }`}
              >
                <td className="py-2 px-2 text-gray-500 whitespace-nowrap">{formatDistanceToNow(r.created_at)}</td>
                <td className="py-2 px-2 text-gray-700 truncate max-w-[100px]">{r.tenant_id}</td>
                <td className="py-2 px-2 text-gray-600">{r.site_id ?? "—"}</td>
                <td className="py-2 px-2 text-gray-600">{r.device_id ?? "—"}</td>
                <td className="py-2 px-2 text-gray-600 truncate max-w-[100px] capitalize">{(r.issue_category || "—").replace(/_/g, " ")}</td>
                <td className="py-2 px-2 text-gray-700 font-medium whitespace-nowrap">{ACTION_LABELS[r.action_type] || r.action_type}</td>
                <td className="py-2 px-2"><StatusBadge status={r.status} /></td>
                <td className="py-2 px-2"><VerificationBadge status={r.verification_status} /></td>
                <td className="py-2 px-2"><EscalationLinkedBadge hasEscalation={!!r.escalation_id} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
