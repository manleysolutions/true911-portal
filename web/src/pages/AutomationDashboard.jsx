import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Zap, Shield, AlertOctagon, AlertTriangle, CheckCircle2, Clock,
  ChevronRight, RefreshCw, Activity, Target, Building2, MapPin,
  ShieldCheck, TrendingDown, Filter, Bell, Wrench, FileText, ArrowRight,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";

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

const SEV = {
  critical: { dot: "bg-red-500", text: "text-red-600", bg: "bg-red-50", border: "border-red-200", label: "Critical" },
  high:     { dot: "bg-amber-500", text: "text-amber-600", bg: "bg-amber-50", border: "border-amber-200", label: "High" },
  medium:   { dot: "bg-blue-500", text: "text-blue-600", bg: "bg-blue-50", border: "border-blue-200", label: "Medium" },
  low:      { dot: "bg-gray-400", text: "text-gray-500", bg: "bg-gray-50", border: "border-gray-200", label: "Low" },
  info:     { dot: "bg-slate-400", text: "text-slate-500", bg: "bg-slate-50", border: "border-slate-200", label: "Info" },
};

const TYPE_ICON = {
  escalate: { icon: AlertOctagon, color: "text-red-500", label: "Escalation" },
  suggest_ping: { icon: Activity, color: "text-blue-500", label: "Ping" },
  suggest_reboot: { icon: Zap, color: "text-amber-500", label: "Reboot" },
  notify: { icon: Bell, color: "text-violet-500", label: "Notification" },
  follow_up: { icon: Wrench, color: "text-orange-500", label: "Follow-up" },
  report_flag: { icon: FileText, color: "text-cyan-500", label: "Report" },
};

const STATUS_STYLE = {
  suggested: { text: "text-blue-600", bg: "bg-blue-50", border: "border-blue-200", label: "Suggested" },
  queued: { text: "text-amber-600", bg: "bg-amber-50", border: "border-amber-200", label: "Queued" },
  suppressed: { text: "text-gray-500", bg: "bg-gray-50", border: "border-gray-200", label: "Suppressed" },
  resolved: { text: "text-emerald-600", bg: "bg-emerald-50", border: "border-emerald-200", label: "Resolved" },
  triggered: { text: "text-violet-600", bg: "bg-violet-50", border: "border-violet-200", label: "Triggered" },
  failed: { text: "text-red-600", bg: "bg-red-50", border: "border-red-200", label: "Failed" },
};

// ═══════════════════════════════════════════════════════════════════
// KPI CARD
// ═══════════════════════════════════════════════════════════════════

function Kpi({ label, value, icon: Icon, color = "text-gray-400", accent }) {
  return (
    <div className={`bg-white rounded-xl border ${accent || "border-gray-200"} p-4`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">{label}</span>
        <Icon className={`w-4 h-4 ${color}`} />
      </div>
      <span className="text-2xl font-bold text-gray-900 tabular-nums">{value ?? 0}</span>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// PRIORITY RECOMMENDATIONS
// ═══════════════════════════════════════════════════════════════════

function RecommendationsList({ items = [] }) {
  const [filter, setFilter] = useState("all");
  const filtered = filter === "all" ? items : items.filter(i => i.severity === filter);

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-blue-500" />
          <h2 className="text-sm font-semibold text-gray-900">Active Recommendations</h2>
        </div>
        <div className="flex items-center gap-2">
          <select value={filter} onChange={e => setFilter(e.target.value)}
            className="text-[11px] px-2 py-1 border border-gray-200 rounded-lg">
            <option value="all">All</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
          </select>
          <span className="text-[11px] text-gray-400 tabular-nums">{filtered.length}</span>
        </div>
      </div>
      <div className="divide-y divide-gray-50 max-h-[500px] overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="px-5 py-10 text-center">
            <CheckCircle2 className="w-7 h-7 text-emerald-500/50 mx-auto mb-2" />
            <p className="text-sm text-emerald-600 font-medium">No active recommendations</p>
            <p className="text-[11px] text-gray-400 mt-1">All automation conditions are clear.</p>
          </div>
        ) : (
          filtered.map((item, i) => {
            const sev = SEV[item.severity] || SEV.info;
            const ti = TYPE_ICON[item.automation_type] || TYPE_ICON.follow_up;
            const TIcon = ti.icon;
            return (
              <div key={item.id || i} className="px-5 py-3.5 hover:bg-gray-50 transition-colors">
                <div className="flex items-start gap-3">
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 mt-2 ${sev.dot}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                      <span className={`text-[9px] font-bold uppercase tracking-wider ${sev.text}`}>{sev.label}</span>
                      <span className={`inline-flex items-center gap-0.5 text-[9px] font-semibold px-1.5 py-0.5 rounded border ${sev.border} ${sev.bg}`}>
                        <TIcon className={`w-2.5 h-2.5 ${ti.color}`} />{ti.label}
                      </span>
                      {item.status && (
                        <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border ${(STATUS_STYLE[item.status] || STATUS_STYLE.suggested).border} ${(STATUS_STYLE[item.status] || STATUS_STYLE.suggested).bg} ${(STATUS_STYLE[item.status] || STATUS_STYLE.suggested).text}`}>
                          {(STATUS_STYLE[item.status] || STATUS_STYLE.suggested).label}
                        </span>
                      )}
                    </div>
                    <p className="text-[13px] text-gray-900 font-medium leading-snug">{item.summary}</p>
                    {item.detail && <p className="text-[11px] text-gray-500 mt-0.5">{item.detail}</p>}
                    <div className="flex items-center gap-2 mt-1.5 text-[10px] text-gray-400">
                      {item.site_id && <span className="flex items-center gap-0.5"><MapPin className="w-2.5 h-2.5" />{item.site_id}</span>}
                      {item.created_at && <span className="flex items-center gap-0.5"><Clock className="w-2.5 h-2.5" />{timeSince(item.created_at)}</span>}
                    </div>
                  </div>
                  {item.site_id && (
                    <Link to={createPageUrl("SiteDetail") + `?site=${item.site_id}`}
                      className="text-[10px] font-medium px-2 py-1 rounded border border-gray-200 text-gray-500 hover:text-gray-700 hover:bg-gray-100 flex-shrink-0">
                      View
                    </Link>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// LIFECYCLE BREAKDOWN
// ═══════════════════════════════════════════════════════════════════

function LifecyclePanel({ byStatus = {} }) {
  const states = ["suggested", "queued", "suppressed", "resolved"];
  const total = Object.values(byStatus).reduce((s, v) => s + v, 0) || 1;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h2 className="text-sm font-semibold text-gray-900 mb-4">Lifecycle Breakdown</h2>
      <div className="space-y-3">
        {states.map(st => {
          const count = byStatus[st] || 0;
          const pct = Math.round((count / total) * 100);
          const style = STATUS_STYLE[st] || STATUS_STYLE.suggested;
          return (
            <div key={st}>
              <div className="flex items-center justify-between mb-1">
                <span className={`text-xs font-medium ${style.text}`}>{style.label}</span>
                <span className="text-xs text-gray-500 tabular-nums">{count}</span>
              </div>
              <div className="w-full bg-gray-100 rounded-full h-1.5">
                <div className={`h-1.5 rounded-full transition-all ${style.text.replace("text-", "bg-").replace("-600", "-500").replace("-500", "-400")}`}
                  style={{ width: `${Math.max(pct, count > 0 ? 3 : 0)}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// TOP ISSUES
// ═══════════════════════════════════════════════════════════════════

function TopIssues({ byReason = [] }) {
  if (byReason.length === 0) return null;
  const LABELS = {
    site_all_offline: "Site offline",
    device_offline: "Device offline",
    stale_heartbeat: "Stale heartbeat",
    partial_reporting: "Partial reporting",
    incident_critical: "Critical incident",
    incident_open: "Open incident",
    e911_incomplete: "E911 incomplete",
    verification_overdue: "Verification overdue",
    signal_degraded: "Signal degraded",
    signal_critical: "Signal critical",
    network_disconnected: "Network disconnected",
    sip_unregistered: "SIP unregistered",
    stale_telemetry: "Stale telemetry",
  };
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h2 className="text-sm font-semibold text-gray-900 mb-3">Top Recurring Issues</h2>
      <div className="space-y-2">
        {byReason.slice(0, 6).map((r, i) => (
          <div key={r.reason} className="flex items-center justify-between">
            <span className="text-xs text-gray-600">{LABELS[r.reason] || r.reason.replace(/_/g, " ")}</span>
            <span className="text-xs font-bold text-gray-900 tabular-nums">{r.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// TOP SITES
// ═══════════════════════════════════════════════════════════════════

function TopSites({ bySite = [] }) {
  if (bySite.length === 0) return null;
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h2 className="text-sm font-semibold text-gray-900 mb-3">Most Impacted Sites</h2>
      <div className="space-y-2">
        {bySite.slice(0, 6).map(s => (
          <Link key={s.site_id} to={createPageUrl("SiteDetail") + `?site=${s.site_id}`}
            className="flex items-center justify-between hover:bg-gray-50 px-2 py-1.5 -mx-2 rounded-lg transition-colors">
            <div className="flex-1 min-w-0">
              <span className="text-xs text-gray-900 font-medium truncate block">{s.site_id}</span>
              {s.latest_summary && <span className="text-[10px] text-gray-400 truncate block">{s.latest_summary}</span>}
            </div>
            <span className="text-xs font-bold text-gray-900 tabular-nums ml-2">{s.count}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// SUPPRESSION INSIGHT
// ═══════════════════════════════════════════════════════════════════

function SuppressionInsight({ suppression = {} }) {
  const total = suppression.total || 0;
  if (total === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="text-sm font-semibold text-gray-900 mb-2">Noise Reduction</h2>
        <div className="text-center py-3">
          <ShieldCheck className="w-6 h-6 text-emerald-500/50 mx-auto mb-1" />
          <p className="text-[11px] text-gray-400">No suppressed events in this period.</p>
        </div>
      </div>
    );
  }
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-900">Noise Reduction</h2>
        <span className="text-lg font-bold text-emerald-600 tabular-nums">{total}</span>
      </div>
      <p className="text-[11px] text-gray-500 mb-3">Duplicate alerts suppressed by deduplication policies.</p>
      {(suppression.top_reasons || []).length > 0 && (
        <div className="space-y-1.5">
          {suppression.top_reasons.slice(0, 4).map(r => (
            <div key={r.reason} className="flex items-center justify-between text-[11px]">
              <span className="text-gray-500">{r.reason.replace(/_/g, " ")}</span>
              <span className="text-gray-700 font-medium tabular-nums">{r.count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// TYPE DISTRIBUTION
// ═══════════════════════════════════════════════════════════════════

function TypeDistribution({ byType = [] }) {
  if (byType.length === 0) return null;
  const total = byType.reduce((s, t) => s + t.count, 0) || 1;
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h2 className="text-sm font-semibold text-gray-900 mb-3">By Automation Type</h2>
      <div className="space-y-2.5">
        {byType.map(t => {
          const ti = TYPE_ICON[t.type] || TYPE_ICON.follow_up;
          const TIcon = ti.icon;
          const pct = Math.round((t.count / total) * 100);
          return (
            <div key={t.type}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  <TIcon className={`w-3 h-3 ${ti.color}`} />
                  <span className="text-xs text-gray-700 font-medium">{ti.label}</span>
                </div>
                <span className="text-[10px] text-gray-400">{t.count} ({pct}%)</span>
              </div>
              <div className="w-full bg-gray-100 rounded-full h-1">
                <div className={`h-1 rounded-full ${ti.color.replace("text-", "bg-")}`} style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// RECENT ACTIVITY
// ═══════════════════════════════════════════════════════════════════

function RecentActivity({ items = [] }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
        <Activity className="w-4 h-4 text-gray-400" />
        <h2 className="text-sm font-semibold text-gray-900">Recent Events</h2>
        <span className="text-[10px] text-gray-400 ml-auto">{items.length}</span>
      </div>
      <div className="divide-y divide-gray-50 max-h-[340px] overflow-y-auto">
        {items.length === 0 ? (
          <div className="px-5 py-8 text-center text-[11px] text-gray-400">No recent automation events.</div>
        ) : (
          items.map((item, i) => {
            const st = STATUS_STYLE[item.status] || STATUS_STYLE.suggested;
            return (
              <div key={item.id || i} className="px-5 py-2.5 flex items-center gap-3">
                <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${(SEV[item.severity] || SEV.info).dot}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-[12px] text-gray-700 truncate">{item.summary}</p>
                </div>
                <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border ${st.border} ${st.bg} ${st.text}`}>{st.label}</span>
                <span className="text-[10px] text-gray-400 flex-shrink-0">{timeSince(item.created_at)}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// MAIN DASHBOARD
// ═══════════════════════════════════════════════════════════════════

export default function AutomationDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hours, setHours] = useState(24);

  const fetchData = useCallback(async () => {
    try {
      const result = await apiFetch(`/command/automation/dashboard?hours=${hours}`);
      setData(result);
    } catch (err) {
      console.error("Automation dashboard fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    setLoading(true);
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <PageWrapper>
        <div className="min-h-screen bg-gray-50 flex items-center justify-center">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-red-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-xs text-gray-400">Loading automation data...</p>
          </div>
        </div>
      </PageWrapper>
    );
  }

  const s = data?.summary || {};

  return (
    <PageWrapper>
      <div className="min-h-screen bg-gray-50">
        <div className="p-5 lg:p-6 max-w-[1400px] mx-auto space-y-5">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-violet-600 rounded-xl flex items-center justify-center shadow-sm">
                <Zap className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-gray-900">Automation</h1>
                <p className="text-[11px] text-gray-400">Operational intelligence & recommendations</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <select value={hours} onChange={e => setHours(Number(e.target.value))}
                className="text-xs px-2.5 py-1.5 border border-gray-200 rounded-lg">
                <option value={6}>Last 6 hours</option>
                <option value={24}>Last 24 hours</option>
                <option value={72}>Last 3 days</option>
                <option value={168}>Last 7 days</option>
              </select>
              <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-100 text-gray-400 transition-colors">
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* KPI Strip */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
            <Kpi label="Active Recommendations" value={s.active_recommendations} icon={Target} color="text-blue-500"
              accent={s.active_recommendations > 0 ? "border-blue-200" : undefined} />
            <Kpi label="Critical Escalations" value={s.critical_escalations} icon={AlertOctagon} color="text-red-500"
              accent={s.critical_escalations > 0 ? "border-red-200" : undefined} />
            <Kpi label="Queued Actions" value={s.queued_actions} icon={Zap} color="text-amber-500" />
            <Kpi label="Suppressed" value={s.suppressed_events} icon={ShieldCheck} color="text-emerald-500" />
            <Kpi label="Resolved" value={s.resolved_today} icon={CheckCircle2} color="text-emerald-500" />
            <Kpi label="Noise Reduction" value={`${s.noise_reduction_pct || 0}%`} icon={TrendingDown} color="text-violet-500" />
          </div>

          {/* Main Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">

            {/* Left — 8/12 */}
            <div className="lg:col-span-8 space-y-5">
              <RecommendationsList items={data?.recommendations || []} />
              <RecentActivity items={data?.recent || []} />
            </div>

            {/* Right — 4/12 */}
            <div className="lg:col-span-4 space-y-5">
              <LifecyclePanel byStatus={data?.by_status || {}} />
              <TypeDistribution byType={data?.by_type || []} />
              <TopIssues byReason={data?.by_reason || []} />
              <TopSites bySite={data?.by_site || []} />
              <SuppressionInsight suppression={data?.suppression || {}} />
            </div>
          </div>
        </div>
      </div>
    </PageWrapper>
  );
}
