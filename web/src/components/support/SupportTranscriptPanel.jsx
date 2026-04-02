import { useRef, useEffect } from "react";
import { Bot, User, Settings, Clock } from "lucide-react";
import { formatTimestamp } from "./utils";

const ROLE_STYLE = {
  user: { icon: User, label: "Customer", bg: "bg-blue-50", border: "border-blue-100", badge: "bg-blue-100 text-blue-700" },
  assistant: { icon: Bot, label: "AI Assistant", bg: "bg-gray-50", border: "border-gray-100", badge: "bg-gray-100 text-gray-700" },
  system: { icon: Settings, label: "System", bg: "bg-amber-50/50", border: "border-amber-100", badge: "bg-amber-100 text-amber-700" },
};

export default function SupportTranscriptPanel({ messages }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages?.length]);

  if (!messages || messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-gray-400">
        Select a session to view the transcript.
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
      {messages.map((msg) => {
        const style = ROLE_STYLE[msg.role] || ROLE_STYLE.system;
        const Icon = style.icon;

        return (
          <div key={msg.id} className={`rounded-lg border ${style.border} ${style.bg} p-3`}>
            {/* Header */}
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-1.5">
                <Icon className="w-3.5 h-3.5 text-gray-500" />
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${style.badge}`}>
                  {style.label}
                </span>
              </div>
              <span className="text-[10px] text-gray-400 flex items-center gap-0.5">
                <Clock className="w-2.5 h-2.5" />
                {formatTimestamp(msg.created_at)}
              </span>
            </div>

            {/* Content */}
            <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
              {msg.content}
            </div>

            {/* Structured response metadata (admin only — shown inline if present) */}
            {msg.structured_response && msg.role === "assistant" && (
              <StructuredBadges data={msg.structured_response} />
            )}
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}

function StructuredBadges({ data }) {
  if (!data) return null;

  const badges = [];
  if (data.issue_category) badges.push({ label: "Category", value: data.issue_category });
  if (data.confidence != null) badges.push({ label: "Confidence", value: `${Math.round(data.confidence * 100)}%` });
  if (data.escalate) badges.push({ label: "Escalation", value: "Recommended", color: "bg-red-100 text-red-700" });

  if (!badges.length) return null;

  return (
    <div className="flex flex-wrap gap-1.5 mt-2 pt-2 border-t border-gray-200/50">
      {badges.map((b) => (
        <span key={b.label} className={`text-[10px] px-1.5 py-0.5 rounded-full ${b.color || "bg-gray-100 text-gray-600"}`}>
          {b.label}: {b.value}
        </span>
      ))}
    </div>
  );
}
