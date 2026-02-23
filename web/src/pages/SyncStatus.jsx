import { useState, useEffect, useCallback, useMemo } from "react";
import { Site } from "@/api/entities";
import { RefreshCw, Search, Download, Calendar, CheckCircle, AlertTriangle, XCircle, Database, Clock, Hash } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";

function timeSince(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const RESULT_STYLES = {
  success: { row: "bg-white", badge: "bg-emerald-50 text-emerald-700 border-emerald-100", icon: CheckCircle, iconColor: "text-emerald-500" },
  warning: { row: "bg-amber-50/30", badge: "bg-amber-50 text-amber-700 border-amber-100", icon: AlertTriangle, iconColor: "text-amber-500" },
  failed:  { row: "bg-red-50/40", badge: "bg-red-50 text-red-700 border-red-200", icon: XCircle, iconColor: "text-red-500" },
};

const SYNC_TYPE_BADGE = {
  HEARTBEAT:     "bg-blue-50 text-blue-700 border-blue-100",
  CONFIG_PUSH:   "bg-purple-50 text-purple-700 border-purple-100",
  E911_UPDATE:   "bg-yellow-50 text-yellow-700 border-yellow-100",
  FIRMWARE_CHECK:"bg-teal-50 text-teal-700 border-teal-100",
  STATUS_POLL:   "bg-gray-100 text-gray-600 border-gray-200",
  CARRIER_SYNC:  "bg-indigo-50 text-indigo-700 border-indigo-100",
  INCIDENT_SYNC: "bg-orange-50 text-orange-700 border-orange-100",
};

function buildDemoSyncEvents(sites) {
  const types = ["HEARTBEAT", "STATUS_POLL", "CONFIG_PUSH", "FIRMWARE_CHECK", "CARRIER_SYNC", "E911_UPDATE"];
  const events = [];
  const now = Date.now();
  for (const site of sites.slice(0, 25)) {
    const count = Math.floor(Math.random() * 4) + 1;
    for (let i = 0; i < count; i++) {
      const ts = now - Math.random() * 86400000 * 3;
      const resultRoll = Math.random();
      const result = resultRoll > 0.15 ? "success" : resultRoll > 0.05 ? "warning" : "failed";
      events.push({
        id: `demo-${site.site_id}-${i}`,
        site_id: site.site_id,
        site_name: site.site_name,
        sync_type: types[Math.floor(Math.random() * types.length)],
        timestamp: new Date(ts).toISOString(),
        result,
        latency_ms: Math.floor(Math.random() * 800) + 50,
        payload_bytes: Math.floor(Math.random() * 4000) + 200,
        requester_id: ["system", "scheduler", "admin@manleysolutions.com"][Math.floor(Math.random() * 3)],
        correlation_id: `COR-${Math.random().toString(36).substr(2, 8).toUpperCase()}`,
        message: result === "success" ? "Sync completed." : result === "warning" ? "Partial sync — retrying." : "Sync failed — device unreachable.",
      });
    }
  }
  return events.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
}

const RESULT_OPTS = ["", "success", "warning", "failed"];
const TYPE_OPTS = ["", "HEARTBEAT", "STATUS_POLL", "CONFIG_PUSH", "FIRMWARE_CHECK", "CARRIER_SYNC", "E911_UPDATE", "INCIDENT_SYNC"];

export default function SyncStatus() {
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterDate, setFilterDate] = useState("");
  const [filterResult, setFilterResult] = useState("");
  const [filterType, setFilterType] = useState("");

  const fetchData = useCallback(async () => {
    const sitesData = await Site.list("-last_checkin", 100);
    setSites(sitesData);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const allEvents = useMemo(() => buildDemoSyncEvents(sites), [sites]);

  const filtered = useMemo(() => {
    return allEvents.filter(ev => {
      if (search) {
        const q = search.toLowerCase();
        if (!ev.site_id?.toLowerCase().includes(q) && !ev.site_name?.toLowerCase().includes(q) && !ev.correlation_id?.toLowerCase().includes(q)) return false;
      }
      if (filterDate && ev.timestamp < filterDate) return false;
      if (filterResult && ev.result !== filterResult) return false;
      if (filterType && ev.sync_type !== filterType) return false;
      return true;
    });
  }, [allEvents, search, filterDate, filterResult, filterType]);

  // Summary stats
  const last24h = allEvents.filter(e => new Date(e.timestamp) > new Date(Date.now() - 86400000));
  const success24h = last24h.filter(e => e.result === "success").length;
  const failed24h = last24h.filter(e => e.result === "failed").length;
  const avgLatency = last24h.length > 0 ? Math.round(last24h.reduce((s, e) => s + (e.latency_ms || 0), 0) / last24h.length) : 0;
  const successPct = last24h.length > 0 ? Math.round((success24h / last24h.length) * 100) : 0;

  const exportCSV = () => {
    const header = "Timestamp,Site ID,Site Name,Sync Type,Result,Latency ms,Payload Bytes,Requester ID,Correlation ID,Message\n";
    const rows = filtered.map(ev =>
      `${ev.timestamp},${ev.site_id},"${ev.site_name}",${ev.sync_type},${ev.result},${ev.latency_ms || ""},${ev.payload_bytes || ""},${ev.requester_id || ""},"${ev.correlation_id || ""}","${(ev.message || "").replace(/"/g, "'")}"`
    ).join("\n");
    const blob = new Blob([header + rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `true911_sync_audit_${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportPDF = () => {
    const win = window.open("", "_blank");
    const rows = filtered.slice(0, 100).map(ev =>
      `<tr class="${ev.result === "failed" ? "row-fail" : ev.result === "warning" ? "row-warn" : ""}">
        <td style="font-size:10px;white-space:nowrap">${new Date(ev.timestamp).toLocaleString()}</td>
        <td>${ev.site_id}</td>
        <td>${ev.site_name}</td>
        <td><span class="badge">${ev.sync_type}</span></td>
        <td><strong>${ev.result}</strong></td>
        <td>${ev.latency_ms || "—"}</td>
        <td>${ev.payload_bytes ? (ev.payload_bytes / 1000).toFixed(1) + "KB" : "—"}</td>
        <td style="font-size:10px">${ev.requester_id || "—"}</td>
        <td style="font-family:monospace;font-size:10px">${ev.correlation_id || "—"}</td>
      </tr>`
    ).join("");
    win.document.write(`
      <html><head><title>True911+ Sync Audit Report</title>
      <style>
        body{font-family:Arial,sans-serif;font-size:11px;padding:20px}
        h1{color:#dc2626}table{border-collapse:collapse;width:100%}
        th{background:#f3f4f6;padding:6px 8px;text-align:left;font-size:10px;border-bottom:2px solid #e5e7eb}
        td{padding:5px 8px;border-bottom:1px solid #f3f4f6;vertical-align:middle}
        .row-fail td{background:#fff5f5}.row-warn td{background:#fffbeb}
        .badge{font-size:9px;padding:1px 5px;border-radius:4px;background:#f3f4f6}
        .summary{display:flex;gap:20px;margin-bottom:16px;padding:12px;background:#f9fafb;border-radius:8px}
        .stat{text-align:center}.stat-val{font-size:20px;font-weight:bold;color:#111}
        .stat-lbl{font-size:10px;color:#6b7280;margin-top:2px}
      </style></head><body>
      <h1>True911+ Sync Audit Report</h1>
      <p style="color:#666;font-size:11px">Generated: ${new Date().toLocaleString()} · ${filtered.length} events</p>
      <div class="summary">
        <div class="stat"><div class="stat-val">${successPct}%</div><div class="stat-lbl">24h Success Rate</div></div>
        <div class="stat"><div class="stat-val" style="color:#dc2626">${failed24h}</div><div class="stat-lbl">24h Failures</div></div>
        <div class="stat"><div class="stat-val">${avgLatency}ms</div><div class="stat-lbl">Avg Latency</div></div>
        <div class="stat"><div class="stat-val">${last24h.length}</div><div class="stat-lbl">24h Events</div></div>
      </div>
      <table><thead><tr><th>Timestamp</th><th>Site ID</th><th>Site Name</th><th>Sync Type</th><th>Result</th><th>Latency</th><th>Payload</th><th>Requester</th><th>Correlation ID</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <p style="margin-top:20px;font-size:10px;color:#999">© 2026 Manley Solutions · True911+ Demo Portal · NDAA-TAA Compliant</p>
      </body></html>
    `);
    win.print();
  };

  return (
    <PageWrapper>
      <div className="p-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Sync Status</h1>
            <p className="text-sm text-gray-500 mt-0.5">Portal sync audit log · Correlation-tracked</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={exportCSV} className="flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-700">
              <Download className="w-3.5 h-3.5" /> CSV
            </button>
            <button onClick={exportPDF} className="flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-700">
              <Download className="w-3.5 h-3.5" /> PDF
            </button>
            <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Sync Summary Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
          {[
            { label: "24h Success Rate", value: `${successPct}%`, color: successPct >= 95 ? "text-emerald-600" : successPct >= 80 ? "text-amber-600" : "text-red-600", icon: CheckCircle },
            { label: "24h Failures", value: failed24h, color: failed24h === 0 ? "text-emerald-600" : "text-red-600", icon: XCircle },
            { label: "Avg Latency", value: `${avgLatency}ms`, color: avgLatency < 300 ? "text-emerald-600" : avgLatency < 600 ? "text-amber-600" : "text-red-600", icon: Clock },
            { label: "24h Events", value: last24h.length, color: "text-gray-700", icon: Database },
          ].map(({ label, value, color, icon: Icon }) => (
            <div key={label} className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-3">
              <Icon className={`w-5 h-5 ${color} flex-shrink-0`} />
              <div>
                <div className={`text-xl font-bold ${color}`}>{value}</div>
                <div className="text-xs text-gray-500 mt-0.5">{label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="bg-white rounded-xl border border-gray-200 p-3 mb-4 flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[180px]">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search site, correlation ID..."
              className="w-full pl-8 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
            />
          </div>
          <div className="flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5 text-gray-400" />
            <input
              type="date"
              value={filterDate}
              onChange={e => setFilterDate(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
            />
          </div>
          <select value={filterResult} onChange={e => setFilterResult(e.target.value)}
            className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-red-500">
            {RESULT_OPTS.map(r => <option key={r} value={r}>{r || "All Results"}</option>)}
          </select>
          <select value={filterType} onChange={e => setFilterType(e.target.value)}
            className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-red-500">
            {TYPE_OPTS.map(t => <option key={t} value={t}>{t || "All Types"}</option>)}
          </select>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100 flex items-center gap-2">
            <Database className="w-4 h-4 text-gray-400" />
            <span className="text-sm font-semibold text-gray-700">{filtered.length} events</span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    <th className="text-left px-4 py-3 font-semibold text-gray-500 uppercase tracking-wide w-5" />
                    <th className="text-left px-3 py-3 font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">Timestamp</th>
                    <th className="text-left px-3 py-3 font-semibold text-gray-500 uppercase tracking-wide">Site</th>
                    <th className="text-left px-3 py-3 font-semibold text-gray-500 uppercase tracking-wide">Sync Type</th>
                    <th className="text-left px-3 py-3 font-semibold text-gray-500 uppercase tracking-wide">Result</th>
                    <th className="text-left px-3 py-3 font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">Latency</th>
                    <th className="text-left px-3 py-3 font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">Payload</th>
                    <th className="text-left px-3 py-3 font-semibold text-gray-500 uppercase tracking-wide">Requester</th>
                    <th className="text-left px-3 py-3 font-semibold text-gray-500 uppercase tracking-wide">Correlation ID</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {filtered.slice(0, 150).map(ev => {
                    const s = RESULT_STYLES[ev.result] || RESULT_STYLES.success;
                    const Icon = s.icon;
                    return (
                      <tr key={ev.id} className={`${s.row} hover:brightness-[0.98] transition-colors`}>
                        <td className="px-4 py-2.5">
                          <Icon className={`w-3.5 h-3.5 ${s.iconColor}`} />
                        </td>
                        <td className="px-3 py-2.5 font-mono text-gray-500 whitespace-nowrap">
                          {new Date(ev.timestamp).toLocaleString()}
                        </td>
                        <td className="px-3 py-2.5">
                          <div className="font-medium text-gray-800 truncate max-w-[150px]">{ev.site_name}</div>
                          <div className="text-gray-400 font-mono">{ev.site_id}</div>
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={`px-2 py-0.5 rounded border text-[10px] font-semibold uppercase ${SYNC_TYPE_BADGE[ev.sync_type] || "bg-gray-100 text-gray-600 border-gray-200"}`}>
                            {ev.sync_type}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={`px-2 py-0.5 rounded border text-[10px] font-bold uppercase ${s.badge}`}>
                            {ev.result}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-gray-600">
                          {ev.latency_ms ? `${ev.latency_ms}ms` : "—"}
                        </td>
                        <td className="px-3 py-2.5 text-gray-600">
                          {ev.payload_bytes ? `${(ev.payload_bytes / 1000).toFixed(1)}KB` : "—"}
                        </td>
                        <td className="px-3 py-2.5 text-gray-500 truncate max-w-[100px]">
                          {ev.requester_id || "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          <span className="font-mono text-gray-400 text-[10px]">{ev.correlation_id || "—"}</span>
                        </td>
                      </tr>
                    );
                  })}
                  {filtered.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-5 py-12 text-center text-sm text-gray-400">
                        No sync events match the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </PageWrapper>
  );
}