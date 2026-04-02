import { useState } from "react";
import { Activity, RefreshCw, ArrowUpRight, CheckCircle, StickyNote, Loader2 } from "lucide-react";

export default function SupportActionsBar({
  session,
  onRunDiagnostics,
  onRefresh,
  onEscalate,
  onMarkResolved,
  loading,
}) {
  const [showEscalateConfirm, setShowEscalateConfirm] = useState(false);
  const [escalateReason, setEscalateReason] = useState("");

  if (!session) return null;

  const isActive = session.status === "active";
  const isEscalated = session.status === "escalated" || session.escalated;

  return (
    <div className="border-t border-gray-200 bg-gray-50 px-3 py-2.5">
      {showEscalateConfirm ? (
        <div className="space-y-2">
          <textarea
            value={escalateReason}
            onChange={(e) => setEscalateReason(e.target.value)}
            placeholder="Escalation reason..."
            className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-red-500"
            rows={2}
          />
          <div className="flex gap-2">
            <button
              onClick={() => {
                onEscalate(escalateReason || "Admin-initiated escalation");
                setShowEscalateConfirm(false);
                setEscalateReason("");
              }}
              disabled={loading}
              className="flex-1 text-xs font-medium bg-red-600 hover:bg-red-700 text-white py-1.5 rounded-lg disabled:opacity-50 flex items-center justify-center gap-1"
            >
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <ArrowUpRight className="w-3 h-3" />}
              Confirm Escalation
            </button>
            <button
              onClick={() => setShowEscalateConfirm(false)}
              className="text-xs text-gray-500 hover:text-gray-700 px-3"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          <ActionButton
            icon={Activity}
            label="Run Diagnostics"
            onClick={onRunDiagnostics}
            disabled={loading}
          />
          <ActionButton
            icon={RefreshCw}
            label="Refresh"
            onClick={onRefresh}
            disabled={loading}
          />
          {isActive && !isEscalated && (
            <ActionButton
              icon={ArrowUpRight}
              label="Escalate"
              onClick={() => setShowEscalateConfirm(true)}
              variant="danger"
              disabled={loading}
            />
          )}
          {isActive && (
            <ActionButton
              icon={CheckCircle}
              label="Mark Resolved"
              onClick={onMarkResolved}
              variant="success"
              disabled={loading}
            />
          )}
          <ActionButton
            icon={StickyNote}
            label="Add Note"
            onClick={() => {/* TODO: admin notes */}}
            variant="muted"
            disabled
            title="Admin notes coming soon"
          />
        </div>
      )}
    </div>
  );
}

function ActionButton({ icon: Icon, label, onClick, variant = "default", disabled, title }) {
  const styles = {
    default: "bg-white border-gray-200 text-gray-700 hover:bg-gray-50",
    danger: "bg-white border-red-200 text-red-700 hover:bg-red-50",
    success: "bg-white border-green-200 text-green-700 hover:bg-green-50",
    muted: "bg-white border-gray-200 text-gray-400",
  };

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`flex items-center gap-1 text-[11px] font-medium px-2.5 py-1.5 border rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${styles[variant]}`}
    >
      <Icon className="w-3 h-3" />
      {label}
    </button>
  );
}
