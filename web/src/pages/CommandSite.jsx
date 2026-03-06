import { useState, useEffect, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Shield, ArrowLeft, Building2, RefreshCw, Clock,
  AlertOctagon, CheckCircle2, ChevronRight, Cpu,
  Wrench, MapPin, Phone,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { apiFetch } from "@/api/client";
import ReadinessScore from "@/components/command/ReadinessScore";

const SEV_STYLE = {
  critical: { bg: "bg-red-900/30", border: "border-red-700/40", text: "text-red-400", dot: "bg-red-500" },
  warning:  { bg: "bg-amber-900/30", border: "border-amber-700/40", text: "text-amber-400", dot: "bg-amber-500" },
  info:     { bg: "bg-blue-900/30", border: "border-blue-700/40", text: "text-blue-400", dot: "bg-blue-500" },
};

const STATUS_BADGE = {
  open:         { label: "Open", cls: "bg-red-500/20 text-red-400 border-red-500/30" },
  acknowledged: { label: "Ack'd", cls: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
  closed:       { label: "Closed", cls: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
};

const PRIORITY_STYLE = {
  high:   "border-red-700/50 bg-red-900/20",
  medium: "border-amber-700/50 bg-amber-900/20",
  low:    "border-slate-700/50 bg-slate-800/50",
};

const PRIORITY_ICON_COLOR = {
  high:   "text-red-400",
  medium: "text-amber-400",
  low:    "text-emerald-400",
};

function timeSince(iso) {
  if (!iso) return "--";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const SITE_STATUS = {
  Connected:        { dot: "bg-emerald-500", text: "text-emerald-400", bg: "bg-emerald-900/20 border-emerald-700/40" },
  "Attention Needed": { dot: "bg-amber-500", text: "text-amber-400", bg: "bg-amber-900/20 border-amber-700/40" },
  "Not Connected":  { dot: "bg-red-500", text: "text-red-400", bg: "bg-red-900/20 border-red-700/40" },
  Unknown:          { dot: "bg-slate-500", text: "text-slate-400", bg: "bg-slate-800/50 border-slate-700/50" },
};

export default function CommandSite() {
  const [searchParams] = useSearchParams();
  const siteId = searchParams.get("site");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    if (!siteId) return;
    try {
      const result = await apiFetch(`/command/site/${siteId}`);
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (!siteId) {
    return (
      <PageWrapper>
        <div className="min-h-screen bg-slate-950 flex items-center justify-center">
          <div className="text-center">
            <p className="text-slate-500">No site specified.</p>
            <Link to={createPageUrl("Command")} className="text-red-500 text-sm mt-2 inline-block">
              Back to Command
            </Link>
          </div>
        </div>
      </PageWrapper>
    );
  }

  if (loading) {
    return (
      <PageWrapper>
        <div className="min-h-screen bg-slate-950 flex items-center justify-center">
          <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
        </div>
      </PageWrapper>
    );
  }

  if (error) {
    return (
      <PageWrapper>
        <div className="min-h-screen bg-slate-950 flex items-center justify-center">
          <div className="text-center">
            <p className="text-red-400 mb-2">{error}</p>
            <Link to={createPageUrl("Command")} className="text-red-500 text-sm">
              Back to Command
            </Link>
          </div>
        </div>
      </PageWrapper>
    );
  }

  const site = data?.site || {};
  const readiness = data?.readiness || {};
  const categories = data?.system_categories || [];
  const incidents = data?.incidents || [];
  const devices = data?.devices || {};
  const actions = data?.recommended_actions || [];
  const sts = SITE_STATUS[site.status] || SITE_STATUS.Unknown;

  const activeIncidents = incidents.filter(i => i.status !== "closed");

  return (
    <PageWrapper>
      <div className="min-h-screen bg-slate-950">
        <div className="p-6 max-w-[1200px] mx-auto space-y-6">

          {/* Back + Header */}
          <div>
            <Link
              to={createPageUrl("Command")}
              className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors mb-4"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Back to Command
            </Link>

            <div className="flex items-start justify-between">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-slate-800 rounded-xl border border-slate-700/50 flex items-center justify-center">
                  <Building2 className="w-6 h-6 text-slate-400" />
                </div>
                <div>
                  <h1 className="text-xl font-bold text-white">{site.site_name || siteId}</h1>
                  <div className="flex items-center gap-3 mt-1">
                    <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold ${sts.bg} ${sts.text}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${sts.dot}`} />
                      {site.status}
                    </div>
                    {site.kit_type && (
                      <span className="text-xs text-slate-500">{site.kit_type}</span>
                    )}
                    {site.customer_name && (
                      <span className="text-xs text-slate-600">{site.customer_name}</span>
                    )}
                  </div>
                </div>
              </div>

              <button onClick={fetchData} className="p-2 rounded-lg border border-slate-700/50 hover:bg-slate-800 text-slate-500">
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Site info bar */}
          {(site.e911_street || site.last_checkin) && (
            <div className="flex flex-wrap items-center gap-4 bg-slate-900 rounded-xl border border-slate-700/50 px-5 py-3">
              {site.e911_street && (
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <MapPin className="w-4 h-4 text-slate-600" />
                  {site.e911_street}, {site.e911_city}, {site.e911_state} {site.e911_zip}
                </div>
              )}
              {site.last_checkin && (
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <Clock className="w-4 h-4 text-slate-600" />
                  Last check-in: {timeSince(site.last_checkin)}
                </div>
              )}
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <Cpu className="w-4 h-4 text-slate-600" />
                {devices.active}/{devices.total} devices active
              </div>
            </div>
          )}

          {/* Main grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

            {/* Left 2/3 */}
            <div className="lg:col-span-2 space-y-5">

              {/* Active Incidents */}
              <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
                <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700/50">
                  <div className="flex items-center gap-2">
                    <AlertOctagon className="w-4 h-4 text-red-500" />
                    <h3 className="text-sm font-semibold text-white">Active Incidents</h3>
                    <span className="text-xs text-slate-500">{activeIncidents.length}</span>
                  </div>
                  <Link
                    to={createPageUrl("Incidents")}
                    className="text-xs text-red-500 hover:text-red-400 font-medium flex items-center gap-0.5"
                  >
                    All <ChevronRight className="w-3 h-3" />
                  </Link>
                </div>
                <div className="divide-y divide-slate-800/50 max-h-[350px] overflow-y-auto">
                  {activeIncidents.length === 0 && (
                    <div className="px-5 py-8 text-center">
                      <CheckCircle2 className="w-8 h-8 text-emerald-500/50 mx-auto mb-2" />
                      <p className="text-sm text-slate-500">No active incidents</p>
                    </div>
                  )}
                  {activeIncidents.map((inc) => {
                    const sev = SEV_STYLE[inc.severity] || SEV_STYLE.info;
                    const stsBadge = STATUS_BADGE[inc.status] || STATUS_BADGE.open;
                    return (
                      <div key={inc.incident_id || inc.id} className="px-5 py-3.5 hover:bg-slate-800/50">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`w-1.5 h-1.5 rounded-full ${sev.dot}`} />
                          <span className={`text-[10px] font-bold uppercase ${sev.text}`}>{inc.severity}</span>
                          <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-bold border ${stsBadge.cls}`}>
                            {stsBadge.label}
                          </span>
                          <span className="text-[10px] text-slate-600 ml-auto">{timeSince(inc.opened_at)}</span>
                        </div>
                        <p className="text-sm text-slate-300">{inc.summary}</p>
                        {inc.assigned_to && (
                          <p className="text-xs text-slate-500 mt-1">Assigned: {inc.assigned_to}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* System Categories */}
              <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-700/50">
                  <h3 className="text-sm font-semibold text-white">System Categories</h3>
                </div>
                <div className="p-5 space-y-3">
                  {categories.map((cat) => {
                    const statusColor = cat.status === "healthy" ? "text-emerald-400" :
                      cat.status === "warning" ? "text-amber-400" : "text-red-400";
                    const statusDot = cat.status === "healthy" ? "bg-emerald-500" :
                      cat.status === "warning" ? "bg-amber-500" : "bg-red-500";
                    return (
                      <div key={cat.key} className="flex items-center justify-between bg-slate-800/50 rounded-lg px-4 py-3 border border-slate-700/30">
                        <div>
                          <p className="text-sm text-slate-200 font-medium">{cat.label}</p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className={`w-1.5 h-1.5 rounded-full ${statusDot}`} />
                            <span className={`text-xs font-semibold capitalize ${statusColor}`}>{cat.status}</span>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-bold text-slate-300">{cat.active_count}/{cat.device_count}</p>
                          <p className="text-xs text-slate-600">devices active</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Recent Activity Timeline */}
              <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-700/50">
                  <h3 className="text-sm font-semibold text-white">Recent Activity</h3>
                </div>
                <div className="p-5 max-h-[300px] overflow-y-auto">
                  {incidents.length === 0 ? (
                    <p className="text-sm text-slate-600 text-center py-4">No recent activity</p>
                  ) : (
                    <div className="space-y-0">
                      {incidents.slice(0, 10).map((inc, i) => {
                        const sev = SEV_STYLE[inc.severity] || SEV_STYLE.info;
                        return (
                          <div key={inc.incident_id || inc.id} className="flex gap-3">
                            <div className="flex flex-col items-center">
                              <div className={`w-2.5 h-2.5 rounded-full ${sev.dot} flex-shrink-0 mt-1.5`} />
                              {i < Math.min(incidents.length, 10) - 1 && (
                                <div className="w-px flex-1 bg-slate-800 my-1" />
                              )}
                            </div>
                            <div className="flex-1 pb-4">
                              <p className="text-sm text-slate-300">{inc.summary}</p>
                              <div className="flex items-center gap-2 mt-1">
                                <span className={`text-[10px] font-bold uppercase ${sev.text}`}>{inc.severity}</span>
                                <span className="text-xs text-slate-600">{timeSince(inc.opened_at)}</span>
                                <span className={`text-[10px] capitalize ${
                                  inc.status === "closed" ? "text-emerald-500" :
                                  inc.status === "acknowledged" ? "text-amber-500" : "text-red-500"
                                }`}>{inc.status}</span>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Right 1/3 */}
            <div className="space-y-5">
              {/* Readiness */}
              <ReadinessScore readiness={readiness} />

              {/* Recommended Actions */}
              <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
                <div className="flex items-center gap-2 px-5 py-4 border-b border-slate-700/50">
                  <Wrench className="w-4 h-4 text-slate-500" />
                  <h3 className="text-sm font-semibold text-white">Recommended Actions</h3>
                </div>
                <div className="p-4 space-y-2">
                  {actions.map((action, i) => (
                    <div
                      key={i}
                      className={`rounded-lg border px-4 py-3 ${PRIORITY_STYLE[action.priority] || PRIORITY_STYLE.low}`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-xs font-bold uppercase ${PRIORITY_ICON_COLOR[action.priority] || "text-slate-400"}`}>
                          {action.priority}
                        </span>
                      </div>
                      <p className="text-sm text-slate-200 font-medium">{action.action}</p>
                      <p className="text-xs text-slate-500 mt-0.5">{action.detail}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </PageWrapper>
  );
}
