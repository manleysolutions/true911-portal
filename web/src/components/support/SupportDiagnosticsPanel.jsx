import { useState } from "react";
import {
  Radio, Cpu, Phone, Activity, Wifi, MapPin,
  AlertOctagon, FileSearch, ChevronDown, ChevronRight,
} from "lucide-react";
import { formatTimestamp, STATUS_COLORS } from "./utils";

const CHECK_META = {
  heartbeat: { icon: Radio, label: "Heartbeat" },
  device_status: { icon: Cpu, label: "Device Status" },
  sip_registration: { icon: Phone, label: "SIP Registration" },
  telemetry: { icon: Activity, label: "Telemetry" },
  ata_reachability: { icon: Wifi, label: "ATA Reachability" },
  incidents: { icon: AlertOctagon, label: "Incidents" },
  e911: { icon: MapPin, label: "E911 Compliance" },
  zoho_ticket: { icon: FileSearch, label: "Zoho Tickets" },
};

export default function SupportDiagnosticsPanel({ diagnostics }) {
  if (!diagnostics || diagnostics.length === 0) {
    return (
      <div className="p-4 text-center">
        <Activity className="w-6 h-6 text-gray-300 mx-auto mb-1.5" />
        <p className="text-xs text-gray-400">No diagnostics run yet.</p>
        <p className="text-[10px] text-gray-400 mt-0.5">Use "Run Diagnostics" to check system status.</p>
      </div>
    );
  }

  // Deduplicate: show latest per check_type
  const latest = {};
  for (const d of diagnostics) {
    if (!latest[d.check_type] || new Date(d.created_at) > new Date(latest[d.check_type].created_at)) {
      latest[d.check_type] = d;
    }
  }
  const items = Object.values(latest);

  return (
    <div className="p-3 space-y-2">
      <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Diagnostics</h3>
      {items.map((d) => (
        <DiagnosticCard key={d.check_type} diagnostic={d} />
      ))}
    </div>
  );
}

function DiagnosticCard({ diagnostic: d }) {
  const [expanded, setExpanded] = useState(false);
  const meta = CHECK_META[d.check_type] || { icon: Activity, label: d.check_type };
  const Icon = meta.icon;
  const colors = STATUS_COLORS[d.status] || STATUS_COLORS.unknown;

  return (
    <div className={`border rounded-lg ${colors.border} overflow-hidden`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className={`w-full flex items-center gap-2 px-3 py-2 text-left ${colors.bg} hover:brightness-95 transition-all`}
      >
        <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
          d.status === "ok" ? "bg-green-500" :
          d.status === "warning" ? "bg-amber-500" :
          d.status === "critical" ? "bg-red-500" : "bg-gray-400"
        }`} />
        <Icon className={`w-3.5 h-3.5 ${colors.text} flex-shrink-0`} />
        <span className={`text-xs font-medium ${colors.text} flex-1`}>{meta.label}</span>
        <span className="text-[10px] text-gray-400">{Math.round(d.confidence * 100)}%</span>
        {expanded ? <ChevronDown className="w-3 h-3 text-gray-400" /> : <ChevronRight className="w-3 h-3 text-gray-400" />}
      </button>

      {expanded && (
        <div className="px-3 py-2 bg-white border-t border-gray-100 space-y-2">
          {/* Customer-safe summary */}
          <div>
            <span className="text-[10px] font-semibold text-gray-400 uppercase">Summary</span>
            <p className="text-xs text-gray-700 mt-0.5">{d.customer_safe_summary}</p>
          </div>

          {/* Internal summary (admin-only) */}
          {d.internal_summary && (
            <div>
              <span className="text-[10px] font-semibold text-amber-600 uppercase">Internal Detail</span>
              <p className="text-xs text-gray-600 mt-0.5 font-mono bg-gray-50 p-1.5 rounded text-[11px]">
                {d.internal_summary}
              </p>
            </div>
          )}

          {/* Raw payload (collapsible debug block) */}
          {d.raw_payload && <RawPayload data={d.raw_payload} />}

          <div className="text-[10px] text-gray-400 text-right">
            {formatTimestamp(d.created_at)}
          </div>
        </div>
      )}
    </div>
  );
}

function RawPayload({ data }) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="text-[10px] text-gray-400 hover:text-gray-600 flex items-center gap-0.5"
      >
        {open ? <ChevronDown className="w-2.5 h-2.5" /> : <ChevronRight className="w-2.5 h-2.5" />}
        Raw Payload
      </button>
      {open && (
        <pre className="text-[10px] text-gray-500 bg-gray-50 p-2 rounded mt-1 overflow-x-auto max-h-40">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
