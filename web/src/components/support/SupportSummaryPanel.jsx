import { Brain, Target, Gauge, AlertTriangle, ListChecks, ShieldAlert, ExternalLink, Link2, Copy } from "lucide-react";

export default function SupportSummaryPanel({ session, messages, escalations }) {
  // Extract latest AI structured response from messages
  const latestAI = [...(messages || [])].reverse().find(
    (m) => m.role === "assistant" && m.structured_response
  );
  const ai = latestAI?.structured_response || {};

  const category = ai.issue_category || session?.issue_category || null;
  const probableCause = ai.probable_cause || null;
  const confidence = ai.confidence != null ? ai.confidence : null;
  const actions = ai.recommended_actions || [];
  const shouldEscalate = ai.escalate || false;
  const escalationReason = ai.escalation_reason || "";

  const hasData = category || probableCause || confidence != null || actions.length > 0;

  if (!hasData && !session) {
    return (
      <div className="p-4 text-center text-sm text-gray-400">
        AI summary will appear here after a conversation.
      </div>
    );
  }

  return (
    <div className="p-3 space-y-3">
      <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider">AI Analysis</h3>

      {/* Issue category */}
      {category && (
        <SummaryRow icon={Target} label="Issue Category">
          <span className="text-xs font-medium text-gray-800 bg-gray-100 px-2 py-0.5 rounded-full capitalize">
            {category.replace(/_/g, " ")}
          </span>
        </SummaryRow>
      )}

      {/* Probable cause (admin-only — shown because this is admin UI) */}
      {probableCause && (
        <SummaryRow icon={Brain} label="Probable Cause">
          <p className="text-xs text-gray-700 leading-relaxed">{probableCause}</p>
        </SummaryRow>
      )}

      {/* Confidence */}
      {confidence != null && (
        <SummaryRow icon={Gauge} label="Confidence">
          <ConfidenceBar value={confidence} />
        </SummaryRow>
      )}

      {/* Recommended actions */}
      {actions.length > 0 && (
        <SummaryRow icon={ListChecks} label="Recommended Actions">
          <ul className="space-y-1">
            {actions.map((a, i) => (
              <li key={i} className="text-xs text-gray-700 flex items-start gap-1.5">
                <span className="w-1 h-1 bg-gray-400 rounded-full mt-1.5 flex-shrink-0" />
                {a}
              </li>
            ))}
          </ul>
        </SummaryRow>
      )}

      {/* Escalation recommendation */}
      {shouldEscalate && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <div className="flex items-center gap-1.5 mb-1">
            <ShieldAlert className="w-3.5 h-3.5 text-red-600" />
            <span className="text-xs font-semibold text-red-700">Escalation Recommended</span>
          </div>
          {escalationReason && (
            <p className="text-xs text-red-600 leading-relaxed">{escalationReason}</p>
          )}
        </div>
      )}

      {/* Session meta */}
      {session && (
        <div className="border-t border-gray-100 pt-3">
          <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Session Info</h4>
          <div className="grid grid-cols-2 gap-y-1.5 text-xs">
            <span className="text-gray-500">Status</span>
            <span className="font-medium text-gray-700 capitalize">{session.status}</span>
            <span className="text-gray-500">Messages</span>
            <span className="font-medium text-gray-700">{session.message_count}</span>
            {session.site_id && <>
              <span className="text-gray-500">Site</span>
              <span className="font-medium text-gray-700">#{session.site_id}</span>
            </>}
            {session.device_id && <>
              <span className="text-gray-500">Device</span>
              <span className="font-medium text-gray-700">#{session.device_id}</span>
            </>}
            <span className="text-gray-500">Tenant</span>
            <span className="font-medium text-gray-700 truncate">{session.tenant_id}</span>
          </div>
        </div>
      )}

      {/* Escalation / Ticket Linkage (admin-only) */}
      {escalations && escalations.length > 0 && (
        <div className="border-t border-gray-100 pt-3">
          <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Escalations</h4>
          <div className="space-y-2">
            {escalations.map((esc) => (
              <EscalationCard key={esc.id} esc={esc} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryRow({ icon: Icon, label, children }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-1">
        <Icon className="w-3 h-3 text-gray-400" />
        <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">{label}</span>
      </div>
      <div className="pl-[18px]">{children}</div>
    </div>
  );
}

function ConfidenceBar({ value }) {
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500";

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-medium text-gray-700 w-8 text-right">{pct}%</span>
    </div>
  );
}

const ESC_STATUS_STYLE = {
  created: "bg-green-50 text-green-700 border-green-200",
  linked: "bg-blue-50 text-blue-700 border-blue-200",
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  failed: "bg-red-50 text-red-700 border-red-200",
};

function EscalationCard({ esc }) {
  const statusStyle = ESC_STATUS_STYLE[esc.status] || ESC_STATUS_STYLE.pending;

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-2.5 space-y-1.5">
      {/* Status + type badges */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${statusStyle}`}>
          {esc.status}
        </span>
        {esc.was_deduplicated && (
          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200 flex items-center gap-0.5">
            <Link2 className="w-2.5 h-2.5" /> Linked
          </span>
        )}
        {esc.escalation_level && (
          <span className="text-[10px] text-gray-500 capitalize">{esc.escalation_level}</span>
        )}
      </div>

      {/* Zoho ticket info */}
      {esc.zoho_ticket_id && (
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-gray-500">Ticket:</span>
          <span className="text-[10px] font-mono font-medium text-gray-700">
            #{esc.zoho_ticket_number || esc.zoho_ticket_id}
          </span>
          {esc.zoho_status && (
            <span className="text-[10px] text-gray-400">({esc.zoho_status})</span>
          )}
          {esc.zoho_ticket_url && (
            <a
              href={esc.zoho_ticket_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] text-blue-600 hover:text-blue-700 flex items-center gap-0.5"
            >
              <ExternalLink className="w-2.5 h-2.5" /> Open
            </a>
          )}
        </div>
      )}

      {/* Sync error */}
      {esc.sync_error && (
        <div className="text-[10px] text-red-600 bg-red-50 px-2 py-1 rounded">
          Sync error: {esc.sync_error}
        </div>
      )}

      {/* Reason (truncated) */}
      <p className="text-[10px] text-gray-500 truncate">{esc.reason}</p>
    </div>
  );
}
