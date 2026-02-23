import { useState, useEffect, useCallback, useMemo } from "react";
import { Site, ActionAudit } from "@/api/entities";
import { FileText, Download, RefreshCw, Filter, Building2, AlertTriangle, ClipboardList } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";

const today = new Date().toISOString().split("T")[0];
const thirtyDaysAgo = new Date(Date.now() - 30 * 86400000).toISOString().split("T")[0];

const REPORT_PRESETS = [
  {
    id: "fleet_inventory",
    label: "Fleet Inventory",
    desc: "All sites: device type, carrier, static IP, E911 summary",
    icon: Building2,
    color: "bg-blue-100 text-blue-700",
  },
  {
    id: "uptime_exceptions",
    label: "Uptime / Health Exceptions",
    desc: "Sites that are not connected, need attention, or are unknown",
    icon: AlertTriangle,
    color: "bg-amber-100 text-amber-700",
  },
  {
    id: "action_audit",
    label: "Action & Audit Report",
    desc: "All portal actions by date, site, user — with correlation IDs",
    icon: ClipboardList,
    color: "bg-purple-100 text-purple-700",
  },
];

export default function Reports() {
  const { user, can } = useAuth();
  const [sites, setSites] = useState([]);
  const [audits, setAudits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeReport, setActiveReport] = useState("fleet_inventory");

  // Filters
  const [filterStatus, setFilterStatus] = useState("");
  const [filterCarrier, setFilterCarrier] = useState("");
  const [filterState, setFilterState] = useState("");
  const [dateStart, setDateStart] = useState(thirtyDaysAgo);
  const [dateEnd, setDateEnd] = useState(today);
  const [filterUser, setFilterUser] = useState("");
  const [filterAction, setFilterAction] = useState("");

  const fetchData = useCallback(async () => {
    const [sitesData, auditData] = await Promise.all([
      Site.list("-last_checkin", 100),
      ActionAudit.list("-timestamp", 200),
    ]);
    setSites(sitesData);
    setAudits(auditData);
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const carriers = [...new Set(sites.map(s => s.carrier).filter(Boolean))];
  const states = [...new Set(sites.map(s => s.e911_state).filter(Boolean))].sort();
  const users = [...new Set(audits.map(a => a.user_email).filter(Boolean))];
  const actionTypes = [...new Set(audits.map(a => a.action_type).filter(Boolean))];

  // Fleet inventory rows
  const fleetRows = useMemo(() => sites.filter(s => {
    if (filterStatus && s.status !== filterStatus) return false;
    if (filterCarrier && s.carrier !== filterCarrier) return false;
    if (filterState && s.e911_state !== filterState) return false;
    return true;
  }), [sites, filterStatus, filterCarrier, filterState]);

  // Uptime exception rows
  const exceptionRows = useMemo(() => sites.filter(s =>
    ["Not Connected", "Attention Needed", "Unknown"].includes(s.status)
  ).filter(s => {
    if (filterCarrier && s.carrier !== filterCarrier) return false;
    if (filterState && s.e911_state !== filterState) return false;
    return true;
  }), [sites, filterCarrier, filterState]);

  // Audit rows
  const auditRows = useMemo(() => audits.filter(a => {
    if (a.timestamp < dateStart || a.timestamp > dateEnd + "T23:59:59") return false;
    if (filterUser && a.user_email !== filterUser) return false;
    if (filterAction && a.action_type !== filterAction) return false;
    return true;
  }), [audits, dateStart, dateEnd, filterUser, filterAction]);

  function timeSince(iso) {
    if (!iso) return "—";
    const diff = Date.now() - new Date(iso);
    const m = Math.floor(diff / 60000);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }

  const exportCSV = () => {
    let csv = "";
    if (activeReport === "fleet_inventory") {
      csv = "Site ID,Site Name,Customer,Status,Endpoint Type,Service Class,Carrier,Network,Static IP,Signal dBm,E911 Street,E911 City,E911 State,E911 ZIP,Device Model,Firmware,Last Check-in\n"
        + fleetRows.map(s => `${s.site_id},"${s.site_name}","${s.customer_name}",${s.status},${s.endpoint_type || s.kit_type || ""},${s.service_class || ""},${s.carrier || ""},${s.network_tech || ""},${s.static_ip || ""},${s.signal_dbm || ""},"${s.e911_street || ""}","${s.e911_city || ""}",${s.e911_state || ""},${s.e911_zip || ""},${s.device_model || ""},${s.device_firmware || ""},${s.last_checkin || ""}`).join("\n");
    } else if (activeReport === "uptime_exceptions") {
      csv = "Site ID,Site Name,Customer,Status,Carrier,Signal dBm,Last Check-in,Days Offline\n"
        + exceptionRows.map(s => {
          const days = s.last_checkin ? Math.floor((Date.now() - new Date(s.last_checkin)) / 86400000) : "";
          return `${s.site_id},"${s.site_name}","${s.customer_name}",${s.status},${s.carrier || ""},${s.signal_dbm || ""},${s.last_checkin || ""},${days}`;
        }).join("\n");
    } else {
      csv = "Audit ID,Timestamp,Site ID,Action,User,Role,Result,Request ID,Details\n"
        + auditRows.map(a => `${a.audit_id || ""},${a.timestamp || ""},${a.site_id || ""},${a.action_type || ""},${a.user_email || ""},${a.role || ""},${a.result || ""},${a.request_id || ""},"${(a.details || "").replace(/"/g, "'")}"`).join("\n");
    }
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `true911_${activeReport}_${today}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportPDF = () => {
    const win = window.open("", "_blank");
    const preset = REPORT_PRESETS.find(r => r.id === activeReport);

    let tableHTML = "";
    if (activeReport === "fleet_inventory") {
      tableHTML = `<table><thead><tr><th>Site ID</th><th>Site Name</th><th>Status</th><th>Type</th><th>Carrier</th><th>IP</th><th>E911</th><th>Last Check-in</th></tr></thead>
      <tbody>${fleetRows.map(s => `<tr><td>${s.site_id}</td><td>${s.site_name}</td><td>${s.status}</td><td>${s.endpoint_type || s.kit_type || ""}</td><td>${s.carrier || ""}</td><td style="font-family:monospace;font-size:10px">${s.static_ip || ""}</td><td>${s.e911_street || ""}${s.e911_city ? ", " + s.e911_city : ""}</td><td>${timeSince(s.last_checkin)}</td></tr>`).join("")}</tbody></table>`;
    } else if (activeReport === "uptime_exceptions") {
      tableHTML = `<table><thead><tr><th>Site ID</th><th>Site Name</th><th>Status</th><th>Carrier</th><th>Signal</th><th>Last Check-in</th></tr></thead>
      <tbody>${exceptionRows.map(s => `<tr style="${s.status === "Not Connected" ? "background:#fff5f5" : s.status === "Attention Needed" ? "background:#fffbeb" : "background:#f9fafb"}"><td>${s.site_id}</td><td>${s.site_name}</td><td><strong>${s.status}</strong></td><td>${s.carrier || ""}</td><td>${s.signal_dbm ? s.signal_dbm + " dBm" : ""}</td><td>${timeSince(s.last_checkin)}</td></tr>`).join("")}</tbody></table>`;
    } else {
      tableHTML = `<table><thead><tr><th>Timestamp</th><th>Site ID</th><th>Action</th><th>User</th><th>Result</th><th>Request ID</th></tr></thead>
      <tbody>${auditRows.slice(0, 100).map(a => `<tr style="${a.result === "fail" ? "background:#fff5f5" : ""}"><td style="font-size:10px;white-space:nowrap">${a.timestamp ? new Date(a.timestamp).toLocaleString() : ""}</td><td>${a.site_id || "—"}</td><td>${a.action_type || ""}</td><td>${a.user_email || ""}</td><td><strong>${a.result || ""}</strong></td><td style="font-family:monospace;font-size:10px">${a.request_id || ""}</td></tr>`).join("")}</tbody></table>`;
    }

    win.document.write(`
      <html><head><title>True911+ ${preset?.label}</title>
      <style>body{font-family:Arial,sans-serif;font-size:11px;padding:24px}h1{color:#dc2626;font-size:20px}h2{color:#374151;font-size:13px;margin-top:20px;border-bottom:1px solid #e5e7eb;padding-bottom:4px}
      .meta{color:#6b7280;font-size:10px;margin-bottom:16px}table{width:100%;border-collapse:collapse;margin-top:8px}
      th{background:#f9fafb;padding:6px 8px;text-align:left;font-size:10px;border-bottom:2px solid #e5e7eb}
      td{padding:5px 8px;border-bottom:1px solid #f3f4f6}footer{margin-top:30px;font-size:10px;color:#9ca3af;border-top:1px solid #e5e7eb;padding-top:10px}</style></head>
      <body>
      <h1>True911+ ${preset?.label}</h1>
      <div class="meta">Generated: ${new Date().toLocaleString()} · By: ${user?.name} (${user?.role}) · Period: ${dateStart} to ${dateEnd}</div>
      ${tableHTML}
      <footer>© 2026 Manley Solutions · True911+ Demo Portal · NDAA-TAA Compliant 🇺🇸</footer>
      </body></html>
    `);
    win.print();
  };

  if (!can("GENERATE_REPORT")) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <div className="text-4xl mb-3">🔒</div>
            <div className="text-lg font-semibold text-gray-800">Access Restricted</div>
            <div className="text-sm text-gray-500 mt-1">Report generation requires Manager or Admin access.</div>
          </div>
        </div>
      </PageWrapper>
    );
  }

  const activePreset = REPORT_PRESETS.find(r => r.id === activeReport);

  return (
    <PageWrapper>
      <div className="p-6 max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Reports</h1>
            <p className="text-sm text-gray-500 mt-0.5">Finance & compliance-ready exports</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={exportCSV} className="flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-700">
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
            <button onClick={exportPDF} className="flex items-center gap-1.5 px-3 py-2 text-sm bg-gray-900 text-white rounded-lg hover:bg-gray-800 font-medium">
              <Download className="w-3.5 h-3.5" /> Generate PDF
            </button>
            <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Report Selector */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
          {REPORT_PRESETS.map(r => {
            const Icon = r.icon;
            const active = activeReport === r.id;
            return (
              <button
                key={r.id}
                onClick={() => setActiveReport(r.id)}
                className={`flex items-start gap-3 p-4 rounded-xl border-2 text-left transition-all ${active ? "border-gray-900 bg-gray-900 text-white shadow-md" : "border-gray-200 bg-white hover:border-gray-300"}`}
              >
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${active ? "bg-white/10" : r.color}`}>
                  <Icon className={`w-4 h-4 ${active ? "text-white" : ""}`} />
                </div>
                <div>
                  <div className={`text-sm font-semibold ${active ? "text-white" : "text-gray-900"}`}>{r.label}</div>
                  <div className={`text-xs mt-0.5 ${active ? "text-gray-300" : "text-gray-500"}`}>{r.desc}</div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Filters */}
        <div className="bg-white rounded-xl border border-gray-200 p-3 mb-4 flex flex-wrap items-center gap-3">
          <Filter className="w-3.5 h-3.5 text-gray-400" />

          {(activeReport === "fleet_inventory") && (
            <>
              <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
                className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-red-500">
                <option value="">All Statuses</option>
                {["Connected", "Not Connected", "Attention Needed", "Unknown"].map(s => <option key={s}>{s}</option>)}
              </select>
              <select value={filterCarrier} onChange={e => setFilterCarrier(e.target.value)}
                className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-red-500">
                <option value="">All Carriers</option>
                {carriers.map(c => <option key={c}>{c}</option>)}
              </select>
              <select value={filterState} onChange={e => setFilterState(e.target.value)}
                className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-red-500">
                <option value="">All States</option>
                {states.map(s => <option key={s}>{s}</option>)}
              </select>
            </>
          )}

          {activeReport === "uptime_exceptions" && (
            <>
              <select value={filterCarrier} onChange={e => setFilterCarrier(e.target.value)}
                className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-red-500">
                <option value="">All Carriers</option>
                {carriers.map(c => <option key={c}>{c}</option>)}
              </select>
              <select value={filterState} onChange={e => setFilterState(e.target.value)}
                className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-red-500">
                <option value="">All States</option>
                {states.map(s => <option key={s}>{s}</option>)}
              </select>
            </>
          )}

          {activeReport === "action_audit" && (
            <>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-500">From</span>
                <input type="date" value={dateStart} onChange={e => setDateStart(e.target.value)}
                  className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" />
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-gray-500">To</span>
                <input type="date" value={dateEnd} onChange={e => setDateEnd(e.target.value)}
                  className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500" />
              </div>
              <select value={filterUser} onChange={e => setFilterUser(e.target.value)}
                className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-red-500">
                <option value="">All Users</option>
                {users.map(u => <option key={u}>{u}</option>)}
              </select>
              <select value={filterAction} onChange={e => setFilterAction(e.target.value)}
                className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-red-500">
                <option value="">All Actions</option>
                {actionTypes.map(a => <option key={a}>{a}</option>)}
              </select>
            </>
          )}
        </div>

        {/* Preview Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100 flex items-center gap-2">
            <FileText className="w-4 h-4 text-gray-400" />
            <span className="text-sm font-semibold text-gray-700">
              {activePreset?.label}
              &nbsp;·&nbsp;
              <span className="font-normal text-gray-500">
                {activeReport === "fleet_inventory" ? fleetRows.length
                  : activeReport === "uptime_exceptions" ? exceptionRows.length
                  : auditRows.length} rows
              </span>
            </span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              {activeReport === "fleet_inventory" && (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      {["Site ID", "Site Name", "Customer", "Status", "Endpoint Type", "Carrier", "Static IP", "Signal dBm", "E911 Summary", "Last Check-in"].map(h => (
                        <th key={h} className="text-left px-4 py-3 font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {fleetRows.map(s => (
                      <tr key={s.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-mono text-gray-500">{s.site_id}</td>
                        <td className="px-3 py-3 font-medium text-gray-900">{s.site_name}</td>
                        <td className="px-3 py-3 text-gray-600">{s.customer_name}</td>
                        <td className="px-3 py-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                            s.status === "Connected" ? "bg-emerald-50 text-emerald-700 border-emerald-100"
                              : s.status === "Not Connected" ? "bg-red-50 text-red-700 border-red-200"
                              : s.status === "Attention Needed" ? "bg-amber-50 text-amber-700 border-amber-200"
                              : "bg-gray-100 text-gray-500 border-gray-200"
                          }`}>{s.status}</span>
                        </td>
                        <td className="px-3 py-3 text-gray-600">{s.endpoint_type || s.kit_type || "—"}</td>
                        <td className="px-3 py-3 text-gray-600">{s.carrier || "—"}</td>
                        <td className="px-3 py-3 font-mono text-gray-500">{s.static_ip || "—"}</td>
                        <td className="px-3 py-3 text-gray-600">{s.signal_dbm ? `${s.signal_dbm} dBm` : "—"}</td>
                        <td className="px-3 py-3 text-gray-500 max-w-[200px] truncate">{[s.e911_street, s.e911_city, s.e911_state].filter(Boolean).join(", ")}</td>
                        <td className="px-3 py-3 text-gray-500 whitespace-nowrap">{timeSince(s.last_checkin)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {activeReport === "uptime_exceptions" && (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      {["Site ID", "Site Name", "Customer", "Status", "Carrier", "Signal", "Last Check-in", "Days Offline"].map(h => (
                        <th key={h} className="text-left px-4 py-3 font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {exceptionRows.map(s => {
                      const days = s.last_checkin ? Math.floor((Date.now() - new Date(s.last_checkin)) / 86400000) : null;
                      return (
                        <tr key={s.id} className={s.status === "Not Connected" ? "bg-red-50/30" : s.status === "Attention Needed" ? "bg-amber-50/30" : "bg-gray-50/40"}>
                          <td className="px-4 py-3 font-mono text-gray-500">{s.site_id}</td>
                          <td className="px-3 py-3 font-medium text-gray-900">{s.site_name}</td>
                          <td className="px-3 py-3 text-gray-600">{s.customer_name}</td>
                          <td className="px-3 py-3">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                              s.status === "Not Connected" ? "bg-red-100 text-red-700 border-red-200"
                                : s.status === "Attention Needed" ? "bg-amber-100 text-amber-700 border-amber-200"
                                : "bg-gray-100 text-gray-500 border-gray-200"
                            }`}>{s.status}</span>
                          </td>
                          <td className="px-3 py-3 text-gray-600">{s.carrier || "—"}</td>
                          <td className="px-3 py-3 text-gray-600">{s.signal_dbm ? `${s.signal_dbm} dBm` : "—"}</td>
                          <td className="px-3 py-3 text-gray-500">{timeSince(s.last_checkin)}</td>
                          <td className="px-3 py-3">
                            {days !== null && <span className={`font-bold ${days > 14 ? "text-red-600" : days > 7 ? "text-amber-600" : "text-gray-600"}`}>{days}d</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}

              {activeReport === "action_audit" && (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      {["Timestamp", "Site ID", "Action", "User", "Role", "Result", "Request ID", "Details"].map(h => (
                        <th key={h} className="text-left px-4 py-3 font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {auditRows.slice(0, 100).map(a => (
                      <tr key={a.id} className={a.result === "fail" ? "bg-red-50/30" : ""}>
                        <td className="px-4 py-3 font-mono text-gray-500 whitespace-nowrap">{a.timestamp ? new Date(a.timestamp).toLocaleString() : "—"}</td>
                        <td className="px-3 py-3 font-mono text-gray-500">{a.site_id || "—"}</td>
                        <td className="px-3 py-3 font-medium text-gray-800">{a.action_type || "—"}</td>
                        <td className="px-3 py-3 text-gray-600">{a.user_email || "—"}</td>
                        <td className="px-3 py-3 text-gray-500">{a.role || "—"}</td>
                        <td className="px-3 py-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${a.result === "success" ? "bg-emerald-50 text-emerald-700 border-emerald-100" : "bg-red-50 text-red-600 border-red-200"}`}>{a.result || "—"}</span>
                        </td>
                        <td className="px-3 py-3 font-mono text-gray-400 text-[10px]">{a.request_id?.slice(-10) || "—"}</td>
                        <td className="px-3 py-3 text-gray-500 max-w-[200px] truncate" title={a.details}>{a.details || "—"}</td>
                      </tr>
                    ))}
                    {auditRows.length === 0 && (
                      <tr><td colSpan={8} className="px-4 py-10 text-center text-gray-400">No audit records match the current filters.</td></tr>
                    )}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      </div>
    </PageWrapper>
  );
}