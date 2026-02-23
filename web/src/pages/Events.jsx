import { useState, useEffect, useCallback } from "react";
import { Event } from "@/api/entities";
import { Activity, Search, RefreshCw, AlertTriangle, Info, AlertOctagon } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";

function timeAgo(iso) {
  if (!iso) return "---";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const SEVERITY_BADGE = {
  critical: "bg-red-50 text-red-700 border-red-200",
  warning: "bg-amber-50 text-amber-700 border-amber-200",
  info: "bg-blue-50 text-blue-700 border-blue-200",
};

const SEVERITY_ICON = {
  critical: AlertOctagon,
  warning: AlertTriangle,
  info: Info,
};

const EVENT_TYPE_LABELS = {
  "device.heartbeat": "Heartbeat",
  "device.registered": "Device Registered",
  "device.offline": "Device Offline",
  "line.registered": "Line Registered",
  "line.down": "Line Down",
  "e911.updated": "E911 Updated",
  "e911.validated": "E911 Validated",
  "alert.triggered": "Alert Triggered",
  "call.started": "Call Started",
  "call.completed": "Call Completed",
  "recording.available": "Recording Available",
  "system.info": "System Info",
};

export default function Events() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  const fetchData = useCallback(async () => {
    const data = await Event.list("-created_at", 500);
    setEvents(data);
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const eventTypes = [...new Set(events.map(e => e.event_type))].sort();

  const filtered = events.filter(e => {
    if (severityFilter && e.severity !== severityFilter) return false;
    if (typeFilter && e.event_type !== typeFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        (e.message || "").toLowerCase().includes(q) ||
        (e.event_type || "").toLowerCase().includes(q) ||
        (e.site_id || "").toLowerCase().includes(q) ||
        (e.device_id || "").toLowerCase().includes(q) ||
        (e.line_id || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  if (loading) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <div className="p-6 max-w-7xl mx-auto space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Events</h1>
            <p className="text-sm text-gray-500 mt-0.5">Unified immutable event log ({events.length} events)</p>
          </div>
          <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search events, messages, site, device, line..."
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm" />
          </div>
          <select value={severityFilter} onChange={e => setSeverityFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm">
            <option value="">All Severity</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </select>
          <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm">
            <option value="">All Types</option>
            {eventTypes.map(t => (
              <option key={t} value={t}>{EVENT_TYPE_LABELS[t] || t}</option>
            ))}
          </select>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {filtered.length === 0 ? (
            <div className="py-16 text-center">
              <Activity className="w-10 h-10 text-gray-300 mx-auto mb-3" />
              <div className="text-sm font-semibold text-gray-500">
                {events.length === 0 ? "No events yet" : "No events match your filters"}
              </div>
              <div className="text-xs text-gray-400 mt-1">
                {events.length === 0
                  ? "Events will appear here as devices register, lines connect, and calls complete."
                  : "Try adjusting your search or filter."}
              </div>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {filtered.map(e => {
                const SevIcon = SEVERITY_ICON[e.severity] || Info;
                return (
                  <div key={e.id} className="flex items-start gap-3 px-4 py-3 hover:bg-gray-50">
                    <div className={`mt-0.5 w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 ${
                      e.severity === "critical" ? "bg-red-100" : e.severity === "warning" ? "bg-amber-100" : "bg-blue-100"
                    }`}>
                      <SevIcon className={`w-3 h-3 ${
                        e.severity === "critical" ? "text-red-600" : e.severity === "warning" ? "text-amber-600" : "text-blue-600"
                      }`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${SEVERITY_BADGE[e.severity] || SEVERITY_BADGE.info}`}>
                          {e.severity}
                        </span>
                        <span className="text-[10px] font-medium bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                          {EVENT_TYPE_LABELS[e.event_type] || e.event_type}
                        </span>
                        {e.site_id && <span className="text-[10px] font-mono text-gray-400">{e.site_id}</span>}
                        {e.device_id && <span className="text-[10px] font-mono text-gray-400">{e.device_id}</span>}
                        {e.line_id && <span className="text-[10px] font-mono text-gray-400">{e.line_id}</span>}
                      </div>
                      <p className="text-sm text-gray-800 mt-0.5">{e.message}</p>
                    </div>
                    <span className="text-xs text-gray-400 flex-shrink-0 whitespace-nowrap">{timeAgo(e.created_at)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </PageWrapper>
  );
}
