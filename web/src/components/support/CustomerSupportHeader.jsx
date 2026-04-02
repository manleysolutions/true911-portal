import { Shield, CheckCircle, AlertCircle, XCircle, Clock, RefreshCw } from "lucide-react";

const STATUS_MAP = {
  operational: {
    label: "Operational",
    icon: CheckCircle,
    color: "text-emerald-700",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    dot: "bg-emerald-500",
  },
  attention: {
    label: "Attention Needed",
    icon: AlertCircle,
    color: "text-amber-700",
    bg: "bg-amber-50",
    border: "border-amber-200",
    dot: "bg-amber-500",
  },
  impacted: {
    label: "Service Impacted",
    icon: XCircle,
    color: "text-red-700",
    bg: "bg-red-50",
    border: "border-red-200",
    dot: "bg-red-500",
  },
};

export function deriveOverallStatus(diagnostics) {
  if (!diagnostics || diagnostics.length === 0) return "operational";

  const hasCritical = diagnostics.some((d) => d.status === "critical");
  if (hasCritical) return "impacted";

  const hasWarning = diagnostics.some((d) => d.status === "warning");
  if (hasWarning) return "attention";

  return "operational";
}

export default function CustomerSupportHeader({ overallStatus, lastChecked, siteName }) {
  const s = STATUS_MAP[overallStatus] || STATUS_MAP.operational;
  const Icon = s.icon;

  const timeLabel = lastChecked
    ? new Date(lastChecked).toLocaleString(undefined, {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
      })
    : null;

  return (
    <div className={`rounded-xl border ${s.border} ${s.bg} px-5 py-4`}>
      <div className="flex items-center justify-between flex-wrap gap-3">
        {/* Status */}
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${s.bg} border ${s.border}`}>
            <Icon className={`w-5 h-5 ${s.color}`} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${s.dot} animate-pulse`} />
              <span className={`text-sm font-semibold ${s.color}`}>{s.label}</span>
            </div>
            <p className="text-xs text-gray-500 mt-0.5">
              {siteName || "Your service"} &middot; {overallStatus === "operational"
                ? "Everything looks good"
                : overallStatus === "attention"
                ? "We noticed something that may need a look"
                : "We're looking into a potential issue"}
            </p>
          </div>
        </div>

        {/* Last checked */}
        {timeLabel && (
          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            <Clock className="w-3 h-3" />
            <span>Last checked {timeLabel}</span>
          </div>
        )}
      </div>
    </div>
  );
}
