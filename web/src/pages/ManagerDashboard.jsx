import { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Shield, Building2, AlertOctagon, Cpu, RefreshCw, ChevronRight,
  Activity, Radio, Clock, Wifi, WifiOff, MapPin, AlertTriangle,
  CheckCircle2, Search, Download, Eye, ChevronDown, ChevronUp,
  ArrowUpRight, ArrowDownRight, Minus, Phone, FileSpreadsheet,
  ShieldCheck, Target,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";
import { statusLabel, statusColor, toCanonical, getAttentionCounts } from "@/lib/attention";

// ═══════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════

function timeSince(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function pctSafe(a, b) {
  if (!b || b === 0) return 0;
  return Math.round((a / b) * 100);
}

// Status colors now come from @/lib/attention (centralized engine)

const API_BASE = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "";

// ═══════════════════════════════════════════════════════════════════
// KPI CARD
// ═══════════════════════════════════════════════════════════════════

function KpiCard({ label, value, sub, icon: Icon, color = "text-slate-400", bgColor = "bg-white", borderColor, trend }) {
  return (
    <div className={`${bgColor} rounded-xl border ${borderColor || "border-gray-200"} p-4 hover:shadow-sm transition-shadow`}>
      <div className="flex items-start justify-between mb-2">
        <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">{label}</span>
        <Icon className={`w-4 h-4 ${color}`} />
      </div>
      <div className="flex items-end gap-1.5">
        <span className="text-2xl font-bold text-gray-900 tabular-nums">{value ?? "—"}</span>
        {trend && (
          <span className={`flex items-center text-[10px] font-semibold mb-0.5 ${
            trend === "up" ? "text-emerald-500" : trend === "down" ? "text-red-500" : "text-gray-400"
          }`}>
            {trend === "up" ? <ArrowUpRight className="w-3 h-3" /> : trend === "down" ? <ArrowDownRight className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
          </span>
        )}
      </div>
      {sub && <p className="text-[11px] text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// ATTENTION NEEDED PANEL
// ═══════════════════════════════════════════════════════════════════

function AttentionPanel({ siteSummaries = [], incidents = [] }) {
  const items = useMemo(() => {
    const list = [];

    // Active incidents (highest priority)
    const activeInc = incidents.filter(i => !["resolved", "dismissed", "closed"].includes(i.status));
    activeInc.forEach(inc => {
      list.push({
        id: `inc-${inc.incident_id || inc.id}`,
        type: "incident",
        severity: inc.severity === "critical" ? "critical" : "warning",
        title: inc.summary,
        site: inc.site_name || inc.site_id,
        siteId: inc.site_id,
        detail: inc.location_detail || `${inc.severity} severity — ${inc.status}`,
        time: inc.opened_at,
      });
    });

    // Sites needing attention (not already covered by incidents)
    const incSiteIds = new Set(activeInc.map(i => i.site_id));
    siteSummaries.filter(s => s.needs_attention && !incSiteIds.has(s.site_id)).forEach(s => {
      const issues = [];
      if (s.stale_devices > 0) issues.push(`${s.stale_devices} device${s.stale_devices > 1 ? "s" : ""} with overdue heartbeat`);
      if (s.overdue_tasks > 0) issues.push(`${s.overdue_tasks} overdue verification task${s.overdue_tasks > 1 ? "s" : ""}`);
      if (s.status === "Not Connected") issues.push("Site not connected");
      list.push({
        id: `site-${s.site_id}`,
        type: "site",
        severity: s.status === "Not Connected" ? "critical" : "warning",
        title: issues.join("; ") || "Needs attention",
        site: s.site_name,
        siteId: s.site_id,
        detail: s.customer_name || "",
        time: s.last_checkin,
      });
    });

    // Sort: critical first, then by time
    list.sort((a, b) => {
      const sevOrder = { critical: 0, warning: 1, info: 2 };
      const sd = (sevOrder[a.severity] ?? 2) - (sevOrder[b.severity] ?? 2);
      if (sd !== 0) return sd;
      if (a.time && b.time) return new Date(b.time) - new Date(a.time);
      return 0;
    });

    return list;
  }, [siteSummaries, incidents]);

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-500" />
          <h2 className="text-sm font-semibold text-gray-900">Attention Needed</h2>
        </div>
        <span className="text-[11px] text-gray-400 tabular-nums">{items.length} item{items.length !== 1 ? "s" : ""}</span>
      </div>
      <div className="divide-y divide-gray-50 max-h-[420px] overflow-y-auto">
        {items.length === 0 ? (
          <div className="px-5 py-10 text-center">
            <CheckCircle2 className="w-7 h-7 text-emerald-500/60 mx-auto mb-2" />
            <p className="text-sm text-emerald-600 font-medium">All clear</p>
            <p className="text-[11px] text-gray-400 mt-1">No issues require your attention right now.</p>
          </div>
        ) : (
          items.slice(0, 10).map(item => (
            <Link
              key={item.id}
              to={createPageUrl("SiteDetail") + `?site=${item.siteId}`}
              className="flex items-start gap-3 px-5 py-3.5 hover:bg-gray-50 transition-colors"
            >
              <div className={`w-2 h-2 rounded-full flex-shrink-0 mt-1.5 ${
                item.severity === "critical" ? "bg-red-500 animate-pulse" : "bg-amber-500"
              }`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className={`text-[9px] font-bold uppercase tracking-wider ${
                    item.severity === "critical" ? "text-red-500" : "text-amber-500"
                  }`}>
                    {item.severity}
                  </span>
                  {item.type === "incident" && (
                    <span className="text-[9px] font-semibold text-red-500 bg-red-50 px-1.5 py-0.5 rounded border border-red-100">INCIDENT</span>
                  )}
                </div>
                <p className="text-[13px] text-gray-900 font-medium leading-snug">{item.title}</p>
                <div className="flex items-center gap-2 mt-1 text-[11px] text-gray-400">
                  <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{item.site}</span>
                  {item.time && (
                    <>
                      <span className="text-gray-200">|</span>
                      <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{timeSince(item.time)}</span>
                    </>
                  )}
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-gray-300 flex-shrink-0 mt-1" />
            </Link>
          ))
        )}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// DEPLOYMENT MAP PREVIEW
// ═══════════════════════════════════════════════════════════════════

function DeploymentMapPreview({ siteSummaries = [] }) {
  const total = siteSummaries.length;
  const critical = siteSummaries.filter(s => s.critical_incidents > 0 || s.status === "Not Connected").length;
  const warning = siteSummaries.filter(s => s.needs_attention && s.critical_incidents === 0 && s.status !== "Not Connected").length;
  const healthy = total - critical - warning;

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-900">Deployment Overview</h2>
        <Link to={createPageUrl("DeploymentMap")} className="text-[11px] text-red-600 hover:text-red-700 font-medium flex items-center gap-0.5">
          Full Map <ChevronRight className="w-3 h-3" />
        </Link>
      </div>
      <div className="p-5">
        <div className="relative h-40 bg-gray-50 rounded-lg overflow-hidden mb-4 border border-gray-100">
          <div className="absolute inset-0 opacity-10">
            <svg width="100%" height="100%" className="text-gray-300">
              {[...Array(8)].map((_, i) => (
                <line key={`h${i}`} x1="0" y1={`${(i+1)*12.5}%`} x2="100%" y2={`${(i+1)*12.5}%`} stroke="currentColor" strokeWidth="0.5" />
              ))}
              {[...Array(12)].map((_, i) => (
                <line key={`v${i}`} x1={`${(i+1)*8.33}%`} y1="0" x2={`${(i+1)*8.33}%`} y2="100%" stroke="currentColor" strokeWidth="0.5" />
              ))}
            </svg>
          </div>
          {siteSummaries.slice(0, 25).map((site, i) => {
            const isCrit = site.critical_incidents > 0 || site.status === "Not Connected";
            const isWarn = site.needs_attention && !isCrit;
            const color = isCrit ? "bg-red-500" : isWarn ? "bg-amber-500" : "bg-emerald-500";
            const x = 6 + ((i * 37 + 13) % 88);
            const y = 8 + ((i * 53 + 7) % 84);
            return (
              <div
                key={site.site_id}
                className={`absolute w-3 h-3 rounded-full ${color} border-2 border-white shadow-sm ${isCrit ? "animate-pulse" : ""}`}
                style={{ left: `${x}%`, top: `${y}%` }}
                title={site.site_name}
              />
            );
          })}
          {total === 0 && (
            <div className="absolute inset-0 flex items-center justify-center">
              <p className="text-[11px] text-gray-400">No sites deployed yet</p>
            </div>
          )}
        </div>
        <div className="flex items-center gap-5 text-[11px]">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
            <span className="text-gray-600">{healthy} Connected</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-amber-500" />
            <span className="text-gray-600">{warning} Attention</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
            <span className="text-gray-600">{critical} Offline</span>
          </div>
          <span className="text-gray-400 ml-auto">{total} total</span>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// SITE STATUS TABLE
// ═══════════════════════════════════════════════════════════════════

function SiteStatusTable({ siteSummaries = [], onPing }) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState("attention"); // attention | name | status | last_checkin
  const [expanded, setExpanded] = useState(true);
  const [pinging, setPinging] = useState(null);

  const filtered = useMemo(() => {
    let list = [...siteSummaries];

    if (search) {
      const q = search.toLowerCase();
      list = list.filter(s =>
        (s.site_name || "").toLowerCase().includes(q) ||
        (s.customer_name || "").toLowerCase().includes(q) ||
        (s.site_id || "").toLowerCase().includes(q)
      );
    }
    if (statusFilter !== "all") {
      if (statusFilter === "attention") list = list.filter(s => s.needs_attention);
      else if (statusFilter === "connected") list = list.filter(s => s.status === "Connected");
      else if (statusFilter === "offline") list = list.filter(s => s.status === "Not Connected");
    }

    list.sort((a, b) => {
      if (sortBy === "attention") {
        const aa = a.needs_attention ? 1 : 0;
        const bb = b.needs_attention ? 1 : 0;
        if (aa !== bb) return bb - aa;
        return (a.site_name || "").localeCompare(b.site_name || "");
      }
      if (sortBy === "name") return (a.site_name || "").localeCompare(b.site_name || "");
      if (sortBy === "status") return (a.status || "").localeCompare(b.status || "");
      if (sortBy === "last_checkin") {
        const ta = a.last_checkin ? new Date(a.last_checkin).getTime() : 0;
        const tb = b.last_checkin ? new Date(b.last_checkin).getTime() : 0;
        return tb - ta;
      }
      return 0;
    });

    return list;
  }, [siteSummaries, search, statusFilter, sortBy]);

  const handlePing = async (siteId) => {
    setPinging(siteId);
    try {
      await onPing(siteId);
    } finally {
      setPinging(null);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div
        className="flex items-center justify-between px-5 py-4 border-b border-gray-100 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <Building2 className="w-4 h-4 text-gray-400" />
          <h2 className="text-sm font-semibold text-gray-900">Site Status</h2>
          <span className="text-[11px] text-gray-400 tabular-nums">{filtered.length} site{filtered.length !== 1 ? "s" : ""}</span>
        </div>
        {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
      </div>

      {expanded && (
        <>
          {/* Filters */}
          <div className="px-5 py-3 border-b border-gray-50 flex flex-wrap gap-2">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-2.5 top-2 w-3.5 h-3.5 text-gray-400" />
              <input
                type="text"
                placeholder="Search sites..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-2 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/20"
            >
              <option value="all">All Status</option>
              <option value="connected">Connected</option>
              <option value="attention">Attention Needed</option>
              <option value="offline">Offline</option>
            </select>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="px-2 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500/20"
            >
              <option value="attention">Priority</option>
              <option value="name">Name</option>
              <option value="status">Status</option>
              <option value="last_checkin">Last Seen</option>
            </select>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/70 border-b border-gray-100">
                  <th className="px-5 py-2.5 text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Site</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Status</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Devices</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Last Seen</th>
                  <th className="px-3 py-2.5 text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Issues</th>
                  <th className="px-3 py-2.5 text-right text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-5 py-8 text-center text-xs text-gray-400">
                      No sites match your filters.
                    </td>
                  </tr>
                )}
                {filtered.map(site => (
                  <tr key={site.site_id} className="hover:bg-gray-50/50 transition-colors">
                    <td className="px-5 py-3">
                      <div>
                        <Link
                          to={createPageUrl("SiteDetail") + `?site=${site.site_id}`}
                          className="text-[13px] font-medium text-gray-900 hover:text-red-600 transition-colors"
                        >
                          {site.site_name}
                        </Link>
                        {site.customer_name && (
                          <p className="text-[11px] text-gray-400 mt-0.5">{site.customer_name}</p>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1.5">
                        <div className={`w-2 h-2 rounded-full ${statusColor(toCanonical(site)).dot}`} />
                        <span className={`text-xs font-medium ${statusColor(toCanonical(site)).text}`}>
                          {statusLabel(toCanonical(site), "manager")}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <span className="text-xs text-gray-600 tabular-nums">{site.total_devices || 0}</span>
                      {site.stale_devices > 0 && (
                        <span className="text-[10px] text-amber-500 ml-1">({site.stale_devices} stale)</span>
                      )}
                    </td>
                    <td className="px-3 py-3">
                      <span className="text-xs text-gray-500">{timeSince(site.last_checkin)}</span>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {site.active_incidents > 0 && (
                          <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-red-50 text-red-600 border border-red-100">
                            {site.active_incidents} incident{site.active_incidents > 1 ? "s" : ""}
                          </span>
                        )}
                        {site.overdue_tasks > 0 && (
                          <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-amber-50 text-amber-600 border border-amber-100">
                            {site.overdue_tasks} overdue
                          </span>
                        )}
                        {!site.active_incidents && !site.overdue_tasks && !site.stale_devices && (
                          <span className="text-[10px] text-gray-300">—</span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => handlePing(site.site_id)}
                          disabled={pinging === site.site_id}
                          className="text-[10px] font-medium px-2 py-1 rounded border border-gray-200 text-gray-500 hover:text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
                          title="Ping this site"
                        >
                          {pinging === site.site_id ? (
                            <div className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" />
                          ) : "Ping"}
                        </button>
                        <Link
                          to={createPageUrl("SiteDetail") + `?site=${site.site_id}`}
                          className="text-[10px] font-medium px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50 transition-colors"
                        >
                          View
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// REPORT EXPORT PANEL
// ═══════════════════════════════════════════════════════════════════

function ReportPanel() {
  const { can } = useAuth();
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      const token = localStorage.getItem("access_token");
      const res = await fetch(`${API_BASE}/api/command/reports/portfolio`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Export failed: ${res.status}`);
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : "true911_report.csv";
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
      toast.success("Report downloaded");
    } catch (err) {
      toast.error(err.message || "Export failed");
    } finally {
      setExporting(false);
    }
  };

  if (!can("COMMAND_EXPORT_REPORTS") && !can("GENERATE_REPORT")) return null;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 mb-3">
        <FileSpreadsheet className="w-4 h-4 text-gray-400" />
        <h2 className="text-sm font-semibold text-gray-900">Reports</h2>
      </div>
      <p className="text-[11px] text-gray-500 mb-4">
        Export a summary of your deployment health, site status, and device reporting compliance.
      </p>
      <button
        onClick={handleExport}
        disabled={exporting}
        className="flex items-center gap-2 px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold rounded-lg transition-colors disabled:opacity-60 w-full justify-center"
      >
        {exporting ? (
          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
        ) : (
          <Download className="w-4 h-4" />
        )}
        {exporting ? "Exporting..." : "Export Portfolio Report"}
      </button>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// READINESS SUMMARY (compact)
// ═══════════════════════════════════════════════════════════════════

function ReadinessSummary({ readiness = {} }) {
  const { score = 0, risk_label = "Operational", factors = [] } = readiness;
  const color = score >= 85 ? "text-emerald-600" : score >= 60 ? "text-amber-600" : "text-red-600";
  const bgColor = score >= 85 ? "bg-emerald-50" : score >= 60 ? "bg-amber-50" : "bg-red-50";
  const borderColor = score >= 85 ? "border-emerald-200" : score >= 60 ? "border-amber-200" : "border-red-200";
  const barColor = score >= 85 ? "bg-emerald-500" : score >= 60 ? "bg-amber-500" : "bg-red-500";

  return (
    <div className={`rounded-xl border ${borderColor} ${bgColor} p-5`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className={`w-4 h-4 ${color}`} />
          <h2 className="text-sm font-semibold text-gray-900">Readiness Score</h2>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-2xl font-bold ${color}`}>{score}</span>
          <span className="text-xs text-gray-400">/100</span>
        </div>
      </div>
      <div className="w-full bg-white/60 rounded-full h-2 mb-3">
        <div className={`h-2 rounded-full transition-all ${barColor}`} style={{ width: `${score}%` }} />
      </div>
      <div className="flex items-center justify-between">
        <span className={`text-xs font-semibold ${color}`}>{risk_label}</span>
        {factors.length > 0 && (
          <span className="text-[10px] text-gray-500">{factors.length} factor{factors.length > 1 ? "s" : ""} affecting score</span>
        )}
      </div>
      {factors.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {factors.slice(0, 3).map((f, i) => (
            <div key={i} className="flex items-center justify-between text-[11px]">
              <span className="text-gray-600">{f.detail || f.label}</span>
              <span className="text-red-500 font-semibold tabular-nums">{f.impact}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// MAIN MANAGER DASHBOARD
// ═══════════════════════════════════════════════════════════════════

export default function ManagerDashboard() {
  const { user, can } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(new Date());

  const fetchData = useCallback(async () => {
    try {
      const result = await apiFetch("/command/summary");
      setData(result);
      setLastRefresh(new Date());
    } catch (err) {
      console.error("Dashboard fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handlePing = useCallback(async (siteId) => {
    try {
      const result = await apiFetch("/actions/ping", {
        method: "POST",
        body: JSON.stringify({ site_id: siteId }),
      });
      if (result.success) {
        toast.success(`Ping successful — ${result.latency_ms || "?"}ms`);
      } else {
        toast.error(result.message || "Ping failed");
      }
      fetchData();
    } catch (err) {
      toast.error(err.message || "Ping failed");
    }
  }, [fetchData]);

  if (loading) {
    return (
      <PageWrapper>
        <div className="min-h-screen bg-gray-50 flex items-center justify-center">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-red-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-xs text-gray-400">Loading dashboard...</p>
          </div>
        </div>
      </PageWrapper>
    );
  }

  const p = data?.portfolio || {};
  const readiness = data?.readiness || {};
  const siteSummaries = data?.site_summaries || [];
  const incidents = data?.incident_feed || [];

  const totalSites = p.total_sites || 0;
  const connectedSites = p.connected_sites || 0;
  const attentionSites = siteSummaries.filter(s => s.needs_attention).length;
  const offlineSites = siteSummaries.filter(s => s.status === "Not Connected").length;
  const totalDevices = p.total_devices || 0;
  const reportingDevices = p.devices_with_telemetry || 0;
  const connectivityPct = totalSites > 0 ? pctSafe(connectedSites, totalSites) : 100;

  return (
    <PageWrapper>
      <div className="min-h-screen bg-gray-50">
        <div className="p-5 lg:p-6 max-w-[1400px] mx-auto space-y-5">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-red-600 rounded-xl flex items-center justify-center shadow-sm">
                <Shield className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-gray-900">Dashboard</h1>
                <p className="text-[11px] text-gray-400">
                  {user?.name} · Deployment overview
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-gray-400 hidden sm:block">{timeSince(lastRefresh.toISOString())}</span>
              <button
                onClick={fetchData}
                className="p-2 rounded-lg border border-gray-200 hover:bg-gray-100 text-gray-400 transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* KPI Strip */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
            <KpiCard
              label="Total Sites" value={totalSites}
              icon={Building2} color="text-gray-400"
              sub={`${p.monitored_sites || 0} with devices`}
            />
            <KpiCard
              label="Connected" value={connectedSites}
              icon={Wifi}
              color={connectivityPct >= 90 ? "text-emerald-500" : "text-amber-500"}
              sub={`${connectivityPct}% connectivity`}
              trend={connectivityPct >= 90 ? "up" : connectivityPct >= 70 ? "neutral" : "down"}
            />
            <KpiCard
              label="Attention Needed" value={attentionSites}
              icon={AlertTriangle}
              color={attentionSites > 0 ? "text-amber-500" : "text-gray-300"}
              borderColor={attentionSites > 0 ? "border-amber-200" : undefined}
              bgColor={attentionSites > 0 ? "bg-amber-50/50" : "bg-white"}
              sub={attentionSites > 0 ? "Sites require follow-up" : "No issues detected"}
            />
            <KpiCard
              label="Offline" value={offlineSites}
              icon={WifiOff}
              color={offlineSites > 0 ? "text-red-500" : "text-gray-300"}
              borderColor={offlineSites > 0 ? "border-red-200" : undefined}
              bgColor={offlineSites > 0 ? "bg-red-50/50" : "bg-white"}
              sub={offlineSites > 0 ? "Sites not connected" : "All sites reachable"}
            />
            <KpiCard
              label="Devices" value={totalDevices}
              icon={Cpu} color="text-blue-500"
              sub={`${reportingDevices} actively reporting`}
            />
            <KpiCard
              label="Readiness" value={`${readiness.score || 0}%`}
              icon={ShieldCheck}
              color={readiness.score >= 85 ? "text-emerald-500" : readiness.score >= 60 ? "text-amber-500" : "text-red-500"}
              sub={readiness.risk_label || "Calculating..."}
            />
          </div>

          {/* Main Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">

            {/* Left Column — 8/12 */}
            <div className="lg:col-span-8 space-y-5">
              <AttentionPanel siteSummaries={siteSummaries} incidents={incidents} />
              <SiteStatusTable siteSummaries={siteSummaries} onPing={handlePing} />
            </div>

            {/* Right Column — 4/12 */}
            <div className="lg:col-span-4 space-y-5">
              <ReadinessSummary readiness={readiness} />
              <DeploymentMapPreview siteSummaries={siteSummaries} />
              <ReportPanel />
            </div>
          </div>
        </div>
      </div>
    </PageWrapper>
  );
}
