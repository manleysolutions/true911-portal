import { useState, useEffect, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Shield, ArrowLeft, Building2, RefreshCw, Clock,
  AlertOctagon, CheckCircle2, ChevronRight, Cpu,
  Wrench, MapPin, Eye, Play, XCircle,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import { toast } from "sonner";
import ReadinessScore from "@/components/command/ReadinessScore";
import ActivityTimeline from "@/components/command/ActivityTimeline";

const SEV_STYLE = {
  critical: { bg: "bg-red-900/30", border: "border-red-700/40", text: "text-red-400", dot: "bg-red-500" },
  warning:  { bg: "bg-amber-900/30", border: "border-amber-700/40", text: "text-amber-400", dot: "bg-amber-500" },
  info:     { bg: "bg-blue-900/30", border: "border-blue-700/40", text: "text-blue-400", dot: "bg-blue-500" },
};

const STATUS_BADGE = {
  new:          { label: "New", cls: "bg-red-500/20 text-red-400 border-red-500/30" },
  open:         { label: "Open", cls: "bg-red-500/20 text-red-400 border-red-500/30" },
  acknowledged: { label: "Ack'd", cls: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
  in_progress:  { label: "In Progress", cls: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
  resolved:     { label: "Resolved", cls: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
  dismissed:    { label: "Dismissed", cls: "bg-slate-500/20 text-slate-400 border-slate-500/30" },
  closed:       { label: "Closed", cls: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
};

const TRANSITIONS = {
  new:          [{ target: "acknowledged", label: "Acknowledge", perm: "COMMAND_ACK", icon: Eye },
                 { target: "dismissed", label: "Dismiss", perm: "COMMAND_DISMISS", icon: XCircle }],
  open:         [{ target: "acknowledged", label: "Acknowledge", perm: "COMMAND_ACK", icon: Eye },
                 { target: "dismissed", label: "Dismiss", perm: "COMMAND_DISMISS", icon: XCircle }],
  acknowledged: [{ target: "in_progress", label: "Start Work", perm: "COMMAND_ASSIGN", icon: Play }],
  in_progress:  [{ target: "resolved", label: "Resolve", perm: "COMMAND_RESOLVE", icon: CheckCircle2 }],
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
  Connected:          { dot: "bg-emerald-500", text: "text-emerald-400", bg: "bg-emerald-900/20 border-emerald-700/40" },
  "Attention Needed": { dot: "bg-amber-500", text: "text-amber-400", bg: "bg-amber-900/20 border-amber-700/40" },
  "Not Connected":    { dot: "bg-red-500", text: "text-red-400", bg: "bg-red-900/20 border-red-700/40" },
  Unknown:            { dot: "bg-slate-500", text: "text-slate-400", bg: "bg-slate-800/50 border-slate-700/50" },
};

export default function CommandSite() {
  const [searchParams] = useSearchParams();
  const { can } = useAuth();
  const siteId = searchParams.get("site");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [acting, setActing] = useState(null);

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

  async function handleTransition(inc, target) {
    const key = `${inc.id}-${target}`;
    setActing(key);
    try {
      await apiFetch(`/command/incidents/${inc.id}/transition/${target}`, { method: "POST", body: JSON.stringify({}) });
      toast.success(`Incident ${target}`);
      fetchData();
    } catch (err) {
      toast.error(err.message || "Action failed");
    } finally {
      setActing(null);
    }
  }

  if (!siteId) {
    return (
      <PageWrapper>
        <div className="min-h-screen bg-slate-950 flex items-center justify-center">
          <div className="text-center">
            <p className="text-slate-500">No site specified.</p>
            <Link to={createPageUrl("Command")} className="text-red-500 text-sm mt-2 inline-block">Back to Command</Link>
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
            <Link to={createPageUrl("Command")} className="text-red-500 text-sm">Back to Command</Link>
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
  const activities = data?.activity_timeline || [];
  const sts = SITE_STATUS[site.status] || SITE_STATUS.Unknown;

  const activeIncidents = incidents.filter(i => !["resolved", "dismissed", "closed"].includes(i.status));

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
                    {site.kit_type && <span className="text-xs text-slate-500">{site.kit_type}</span>}
                    {site.customer_name && <span className="text-xs text-slate-600">{site.customer_name}</span>}
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

              {/* Active Incidents with actions */}
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
                <div className="divide-y divide-slate-800/50 max-h-[400px] overflow-y-auto">
                  {activeIncidents.length === 0 && (
                    <div className="px-5 py-8 text-center">
                      <CheckCircle2 className="w-8 h-8 text-emerald-500/50 mx-auto mb-2" />
                      <p className="text-sm text-slate-500">No active incidents</p>
                    </div>
                  )}
                  {activeIncidents.map((inc) => {
                    const sev = SEV_STYLE[inc.severity] || SEV_STYLE.info;
                    const stsBadge = STATUS_BADGE[inc.status] || STATUS_BADGE.open;
                    const availableActions = (TRANSITIONS[inc.status] || []).filter(t => can(t.perm));

                    return (
                      <div key={inc.incident_id || inc.id} className="px-5 py-3.5 hover:bg-slate-800/50">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`w-1.5 h-1.5 rounded-full ${sev.dot}`} />
                          <span className={`text-[10px] font-bold uppercase ${sev.text}`}>{inc.severity}</span>
                          <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-bold border ${stsBadge.cls}`}>
                            {stsBadge.label}
                          </span>
                          {inc.incident_type && (
                            <span className="text-[10px] text-slate-600">{inc.incident_type}</span>
                          )}
                          <span className="text-[10px] text-slate-600 ml-auto">{timeSince(inc.opened_at)}</span>
                        </div>
                        <p className="text-sm text-slate-300">{inc.summary}</p>
                        {inc.location_detail && (
                          <p className="text-xs text-slate-600 mt-0.5">{inc.location_detail}</p>
                        )}
                        {inc.assigned_to && (
                          <p className="text-xs text-slate-500 mt-1">Assigned: {inc.assigned_to}</p>
                        )}

                        {availableActions.length > 0 && (
                          <div className="flex items-center gap-2 mt-2">
                            {availableActions.map((action) => {
                              const ActionIcon = action.icon;
                              const isActing = acting === `${inc.id}-${action.target}`;
                              return (
                                <button
                                  key={action.target}
                                  onClick={() => handleTransition(inc, action.target)}
                                  disabled={isActing}
                                  className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors border
                                    ${action.target === "dismissed"
                                      ? "border-slate-600 text-slate-400 hover:bg-slate-800"
                                      : action.target === "resolved"
                                      ? "border-emerald-700/50 text-emerald-400 hover:bg-emerald-900/30"
                                      : "border-slate-600 text-slate-300 hover:bg-slate-700"
                                    }
                                    ${isActing ? "opacity-50 cursor-not-allowed" : ""}
                                  `}
                                >
                                  {isActing
                                    ? <div className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" />
                                    : <ActionIcon className="w-3 h-3" />
                                  }
                                  {action.label}
                                </button>
                              );
                            })}
                          </div>
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

              {/* Activity Timeline */}
              <ActivityTimeline activities={activities} />
            </div>

            {/* Right 1/3 */}
            <div className="space-y-5">
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
