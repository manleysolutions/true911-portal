/**
 * Status and verification badges for remediation records.
 * Shared across SelfHealingConsole components.
 */

const STATUS_STYLE = {
  succeeded: "bg-green-50 text-green-700 border-green-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  running: "bg-blue-50 text-blue-700 border-blue-200",
  pending: "bg-gray-50 text-gray-600 border-gray-200",
  blocked: "bg-orange-50 text-orange-700 border-orange-200",
  cooldown: "bg-amber-50 text-amber-700 border-amber-200",
  queued: "bg-gray-50 text-gray-500 border-gray-200",
};

const VERIFICATION_STYLE = {
  passed: "bg-green-50 text-green-700 border-green-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  skipped: "bg-gray-50 text-gray-500 border-gray-200",
};

export function StatusBadge({ status }) {
  const s = STATUS_STYLE[status] || STATUS_STYLE.pending;
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border capitalize ${s}`}>
      {status}
    </span>
  );
}

export function VerificationBadge({ status }) {
  if (!status) return <span className="text-[10px] text-gray-400">—</span>;
  const s = VERIFICATION_STYLE[status] || VERIFICATION_STYLE.pending;
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border capitalize ${s}`}>
      {status}
    </span>
  );
}

export function ActionLevelBadge({ level }) {
  const styles = {
    safe: "bg-green-50 text-green-600 border-green-200",
    low_risk: "bg-blue-50 text-blue-600 border-blue-200",
    gated: "bg-purple-50 text-purple-600 border-purple-200",
  };
  const s = styles[level] || styles.safe;
  return (
    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full border ${s}`}>
      {(level || "safe").replace("_", " ")}
    </span>
  );
}

export function EscalationLinkedBadge({ hasEscalation }) {
  if (!hasEscalation) return null;
  return (
    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full border bg-red-50 text-red-700 border-red-200">
      Escalated
    </span>
  );
}

export function DeviceHealthBadge({ label }) {
  const styles = {
    "Stable": "bg-green-50 text-green-700 border-green-200",
    "Recovering": "bg-blue-50 text-blue-700 border-blue-200",
    "Repeated Failures": "bg-red-50 text-red-700 border-red-200",
    "Escalated": "bg-red-50 text-red-600 border-red-200",
    "Cooldown Heavy": "bg-amber-50 text-amber-700 border-amber-200",
    "Manual Review Needed": "bg-orange-50 text-orange-700 border-orange-200",
  };
  const s = styles[label] || "bg-gray-50 text-gray-600 border-gray-200";
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${s}`}>
      {label}
    </span>
  );
}
