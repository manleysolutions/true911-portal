import { formatDistanceToNow } from "@/components/support/utils";
import { AlertTriangle, CheckCircle, ArrowUpRight, MessageSquare, Clock } from "lucide-react";

const STATUS_BADGE = {
  active: "bg-blue-50 text-blue-700 border-blue-200",
  resolved: "bg-green-50 text-green-700 border-green-200",
  escalated: "bg-red-50 text-red-700 border-red-200",
};

const STATUS_ICON = {
  active: MessageSquare,
  resolved: CheckCircle,
  escalated: ArrowUpRight,
};

export default function SupportSessionQueue({ sessions, selectedId, onSelect, loading }) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-40">
        <div className="w-5 h-5 border-2 border-gray-300 border-t-red-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (!sessions.length) {
    return (
      <div className="px-4 py-8 text-center">
        <MessageSquare className="w-8 h-8 text-gray-300 mx-auto mb-2" />
        <p className="text-sm text-gray-500">No support sessions found</p>
        <p className="text-xs text-gray-400 mt-1">Sessions will appear here when customers start a conversation.</p>
      </div>
    );
  }

  return (
    <div className="divide-y divide-gray-100 overflow-y-auto">
      {sessions.map((s) => {
        const isSelected = s.id === selectedId;
        const StatusIcon = STATUS_ICON[s.status] || MessageSquare;

        return (
          <button
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`w-full text-left px-3 py-3 transition-colors hover:bg-gray-50 ${
              isSelected ? "bg-red-50/50 border-l-2 border-l-red-500" : "border-l-2 border-l-transparent"
            }`}
          >
            {/* Top row: tenant + status */}
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-gray-700 truncate max-w-[140px]">
                {s.tenant_id}
              </span>
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${STATUS_BADGE[s.status] || "bg-gray-50 text-gray-600 border-gray-200"}`}>
                {s.status}
              </span>
            </div>

            {/* Category + escalated flag */}
            <div className="flex items-center gap-1.5 mb-1">
              <StatusIcon className="w-3 h-3 text-gray-400 flex-shrink-0" />
              <span className="text-xs text-gray-600 truncate">
                {s.issue_category || "General inquiry"}
              </span>
              {s.escalated && (
                <AlertTriangle className="w-3 h-3 text-red-500 flex-shrink-0" />
              )}
            </div>

            {/* Bottom row: messages count + time */}
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-400">
                {s.message_count} msg{s.message_count !== 1 ? "s" : ""}
                {s.site_id ? ` · Site ${s.site_id}` : ""}
                {s.device_id ? ` · Dev ${s.device_id}` : ""}
              </span>
              <span className="text-[10px] text-gray-400 flex items-center gap-0.5">
                <Clock className="w-2.5 h-2.5" />
                {formatDistanceToNow(s.updated_at)}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
