import { Shield, AlertTriangle, CheckCircle, XCircle, Clock } from "lucide-react";
import { formatDistanceToNow } from "./utils";
import { StatusBadge, VerificationBadge } from "./RecoveryStatusBadge";

/**
 * Life-safety-focused view of remediation activity.
 * Filters to elevator, fire alarm, emergency phone, and critical device issues.
 * Highlights failed remediations and unresolved escalations.
 */

const LIFE_SAFETY_CATEGORIES = new Set([
  "device_offline",
  "voice_quality",
  "connectivity_warning",
  "heartbeat_missed",
]);

export default function LifeSafetyRecoveryPanel({ records }) {
  // Filter to life-safety-relevant records
  const lsRecords = (records || []).filter((r) =>
    LIFE_SAFETY_CATEGORIES.has(r.issue_category) || r.escalation_id
  );

  // Split into active concerns vs resolved
  const active = lsRecords.filter((r) => r.status === "failed" || r.verification_status === "failed" || r.status === "running");
  const recent = lsRecords.filter((r) => r.status === "succeeded").slice(0, 10);
  const blocked = lsRecords.filter((r) => r.status === "blocked" || r.status === "cooldown");

  const hasIssues = active.length > 0 || blocked.length > 0;

  return (
    <div className="space-y-4">
      {/* Status banner */}
      <div className={`flex items-center gap-3 p-3 rounded-lg border ${
        hasIssues
          ? "bg-red-50 border-red-200"
          : "bg-green-50 border-green-200"
      }`}>
        {hasIssues
          ? <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0" />
          : <Shield className="w-5 h-5 text-green-600 flex-shrink-0" />
        }
        <div>
          <p className={`text-sm font-semibold ${hasIssues ? "text-red-700" : "text-green-700"}`}>
            {hasIssues
              ? `${active.length} active issue${active.length !== 1 ? "s" : ""} on life-safety endpoints`
              : "No active life-safety recovery issues"
            }
          </p>
          <p className="text-[10px] text-gray-500 mt-0.5">
            {lsRecords.length} total remediation{lsRecords.length !== 1 ? "s" : ""} on life-safety endpoints
            {blocked.length > 0 ? ` · ${blocked.length} blocked/cooldown` : ""}
          </p>
        </div>
      </div>

      {/* Active concerns */}
      {active.length > 0 && (
        <div>
          <h4 className="text-[10px] font-bold text-red-600 uppercase tracking-wider mb-2 flex items-center gap-1">
            <XCircle className="w-3 h-3" /> Active Issues
          </h4>
          <div className="space-y-1.5">
            {active.map((r) => (
              <RecoveryRow key={r.id} record={r} variant="danger" />
            ))}
          </div>
        </div>
      )}

      {/* Blocked */}
      {blocked.length > 0 && (
        <div>
          <h4 className="text-[10px] font-bold text-amber-600 uppercase tracking-wider mb-2 flex items-center gap-1">
            <Clock className="w-3 h-3" /> Blocked / Cooldown
          </h4>
          <div className="space-y-1.5">
            {blocked.slice(0, 5).map((r) => (
              <RecoveryRow key={r.id} record={r} variant="warning" />
            ))}
          </div>
        </div>
      )}

      {/* Recently recovered */}
      {recent.length > 0 && (
        <div>
          <h4 className="text-[10px] font-bold text-green-600 uppercase tracking-wider mb-2 flex items-center gap-1">
            <CheckCircle className="w-3 h-3" /> Recently Recovered
          </h4>
          <div className="space-y-1.5">
            {recent.slice(0, 5).map((r) => (
              <RecoveryRow key={r.id} record={r} variant="success" />
            ))}
          </div>
        </div>
      )}

      {lsRecords.length === 0 && (
        <p className="text-xs text-gray-400 text-center py-4">
          No life-safety remediation activity found.
        </p>
      )}
    </div>
  );
}

function RecoveryRow({ record: r, variant }) {
  const borderColor = {
    danger: "border-l-red-500",
    warning: "border-l-amber-500",
    success: "border-l-green-500",
  }[variant] || "border-l-gray-300";

  return (
    <div className={`bg-white border border-gray-200 rounded-lg px-3 py-2 border-l-2 ${borderColor}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-gray-700 capitalize">
          {(r.action_type || "").replace(/_/g, " ")}
        </span>
        <div className="flex items-center gap-1.5">
          <StatusBadge status={r.status} />
          <VerificationBadge status={r.verification_status} />
        </div>
      </div>
      <div className="flex items-center gap-3 text-[10px] text-gray-500">
        <span>Site {r.site_id ?? "—"}</span>
        <span>Device {r.device_id ?? "—"}</span>
        <span className="capitalize">{(r.issue_category || "").replace(/_/g, " ")}</span>
        <span className="ml-auto">{formatDistanceToNow(r.created_at)}</span>
      </div>
      {r.blocked_reason && (
        <p className="text-[10px] text-amber-600 mt-1 truncate">{r.blocked_reason}</p>
      )}
    </div>
  );
}
