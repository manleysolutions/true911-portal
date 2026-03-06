import { useState, useEffect } from "react";
import { Signal, SignalZero, SignalLow, SignalMedium, Wifi, WifiOff, Radio, Loader2 } from "lucide-react";
import { apiFetch } from "@/api/client";

function signalIcon(status) {
  if (!status) return <Signal className="w-4 h-4 text-gray-400" />;
  const s = status.toLowerCase();
  if (["disconnected", "not_registered", "denied"].includes(s))
    return <WifiOff className="w-4 h-4 text-red-500" />;
  if (["connected", "registered", "attached"].includes(s))
    return <Wifi className="w-4 h-4 text-emerald-500" />;
  return <SignalLow className="w-4 h-4 text-amber-500" />;
}

function severityColor(sev) {
  if (sev === "critical") return "bg-red-100 text-red-700";
  if (sev === "warning") return "bg-amber-100 text-amber-700";
  return "bg-blue-100 text-blue-700";
}

export default function NetworkStatus({ siteId }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch(`/command/network-events?site_id=${siteId}&limit=10`)
      .then(setEvents)
      .catch(() => setEvents([]))
      .finally(() => setLoading(false));
  }, [siteId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-2">
        <Radio className="w-4 h-4 text-blue-600" />
        <h3 className="text-sm font-semibold text-gray-900">Network Events</h3>
        <span className="text-[10px] text-gray-400 ml-auto">{events.length} recent</span>
      </div>

      {events.length === 0 ? (
        <p className="text-xs text-gray-500 text-center py-4">No network events recorded.</p>
      ) : (
        <div className="space-y-1.5">
          {events.map(evt => (
            <div key={evt.id} className="flex items-start gap-2 p-2.5 bg-gray-50 rounded-lg">
              {signalIcon(evt.network_status)}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-gray-900 truncate">{evt.summary}</span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${severityColor(evt.severity)}`}>
                    {evt.severity}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[10px] text-gray-500">{evt.event_type.replace(/_/g, " ")}</span>
                  {evt.carrier && <span className="text-[10px] text-gray-400">• {evt.carrier}</span>}
                  {evt.signal_dbm != null && (
                    <span className="text-[10px] text-gray-400">• {evt.signal_dbm} dBm</span>
                  )}
                </div>
                <div className="text-[10px] text-gray-400 mt-0.5">
                  {new Date(evt.created_at).toLocaleString()}
                  {evt.resolved && <span className="text-emerald-600 ml-1 font-semibold">Resolved</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
