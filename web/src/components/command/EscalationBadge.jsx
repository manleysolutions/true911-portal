import { ArrowUpCircle, Clock } from "lucide-react";

function minutesSince(iso) {
  if (!iso) return 0;
  return Math.floor((Date.now() - new Date(iso)) / 60000);
}

export default function EscalationBadge({ incident }) {
  const level = incident.escalation_level || 0;
  const isUnacked = ["new", "open"].includes(incident.status);
  const minutesOpen = minutesSince(incident.opened_at);

  if (level > 0) {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide border border-orange-600/50 bg-orange-900/30 text-orange-400">
        <ArrowUpCircle className="w-3 h-3" />
        L{level}
      </span>
    );
  }

  if (isUnacked && minutesOpen >= 15) {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border border-amber-700/40 bg-amber-900/20 text-amber-500">
        <Clock className="w-3 h-3" />
        {minutesOpen}m
      </span>
    );
  }

  return null;
}
