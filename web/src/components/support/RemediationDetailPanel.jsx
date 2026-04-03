import { useState } from "react";
import { Clock, Shield, CheckCircle, XCircle, Link2, ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
import { formatTimestamp } from "./utils";
import { StatusBadge, VerificationBadge, ActionLevelBadge } from "./RecoveryStatusBadge";

export default function RemediationDetailPanel({ record }) {
  if (!record) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-gray-400 p-4">
        Select a remediation action to view details.
      </div>
    );
  }

  const r = record;

  return (
    <div className="p-3 space-y-4 overflow-y-auto">
      {/* 1. Summary */}
      <DetailSection title="Summary" icon={Shield}>
        <DetailRow label="Action" value={r.action_type?.replace(/_/g, " ")} />
        <DetailRow label="Issue" value={r.issue_category?.replace(/_/g, " ") || "—"} />
        <DetailRow label="Trigger" value={r.trigger_source} />
        <DetailRow label="Level"><ActionLevelBadge level={r.action_level} /></DetailRow>
        <DetailRow label="Status"><StatusBadge status={r.status} /></DetailRow>
        <DetailRow label="Started" value={formatTimestamp(r.started_at) || "—"} />
        <DetailRow label="Completed" value={formatTimestamp(r.completed_at) || "—"} />
        <DetailRow label="Attempt" value={r.attempt_count} />
      </DetailSection>

      {/* 2. Policy Decision */}
      {(r.blocked_reason || r.status === "blocked" || r.status === "cooldown") && (
        <DetailSection title="Policy Decision" icon={Clock}>
          <DetailRow label="Result" value={r.status === "blocked" ? "Blocked" : "Cooldown"} />
          {r.blocked_reason && (
            <div className="text-xs text-orange-700 bg-orange-50 border border-orange-200 rounded-lg p-2 mt-1">
              {r.blocked_reason}
            </div>
          )}
        </DetailSection>
      )}

      {/* 3. Verification */}
      <DetailSection title="Verification" icon={r.verification_status === "passed" ? CheckCircle : XCircle}>
        <DetailRow label="Status"><VerificationBadge status={r.verification_status} /></DetailRow>
        {r.verification_summary && (
          <p className="text-xs text-gray-600 mt-1 leading-relaxed">{r.verification_summary}</p>
        )}
      </DetailSection>

      {/* 4. Related Context */}
      <DetailSection title="Related Context" icon={Link2}>
        <DetailRow label="Tenant" value={r.tenant_id} />
        <DetailRow label="Site" value={r.site_id ?? "—"} />
        <DetailRow label="Device" value={r.device_id ?? "—"} />
        {r.session_id && <DetailRow label="Session" value={String(r.session_id).slice(0, 8) + "…"} />}
        {r.escalation_id && (
          <DetailRow label="Escalation" value={
            <span className="text-red-600 font-medium text-xs">{String(r.escalation_id).slice(0, 8)}…</span>
          } />
        )}
      </DetailSection>

      {/* 5. Raw Result (collapsible) */}
      {r.raw_result && <RawResultBlock data={r.raw_result} />}
    </div>
  );
}

function DetailSection({ title, icon: Icon, children }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <Icon className="w-3.5 h-3.5 text-gray-400" />
        <h4 className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">{title}</h4>
      </div>
      <div className="pl-[20px] space-y-1">{children}</div>
    </div>
  );
}

function DetailRow({ label, value, children }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-gray-500">{label}</span>
      <span className="font-medium text-gray-700 text-right max-w-[160px] truncate capitalize">
        {children || value}
      </span>
    </div>
  );
}

function RawResultBlock({ data }) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-600"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        Raw Internal Result
      </button>
      {open && (
        <pre className="text-[10px] text-gray-500 bg-gray-50 border border-gray-200 p-2 rounded mt-1 overflow-x-auto max-h-48">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
