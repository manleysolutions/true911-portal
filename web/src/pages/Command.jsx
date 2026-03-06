import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import {
  Shield, Building2, AlertOctagon, Cpu, RefreshCw,
  ChevronRight, Zap, Eye, Activity, Radio,
} from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { apiFetch } from "@/api/client";
import IncidentFeed from "@/components/command/IncidentFeed";
import SystemHealthMatrix from "@/components/command/SystemHealthMatrix";
import ReadinessScore from "@/components/command/ReadinessScore";
import ScenarioRunner from "@/components/command/ScenarioRunner";
import ActivityTimeline from "@/components/command/ActivityTimeline";

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

function KPICard({ label, value, sub, icon: Icon, color, border }) {
  return (
    <div className={`bg-slate-900 rounded-xl border ${border || "border-slate-700/50"} p-4`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">{label}</span>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${color}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <div className="text-3xl font-bold text-white">{value ?? "--"}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}

export default function Command() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [showScenario, setShowScenario] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const result = await apiFetch("/command/summary");
      setData(result);
      setLastRefresh(new Date());
    } catch (err) {
      console.error("Command summary fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <PageWrapper>
        <div className="flex items-center justify-center h-64">
          <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
        </div>
      </PageWrapper>
    );
  }

  const p = data?.portfolio || {};
  const readiness = data?.readiness || {};
  const systemHealth = data?.system_health || [];
  const incidents = data?.incident_feed || [];
  const attentionSites = data?.attention_sites_list || [];
  const activities = data?.activity_timeline || [];

  return (
    <PageWrapper>
      <div className="min-h-screen bg-slate-950">
        <div className="p-6 max-w-[1400px] mx-auto space-y-6">

          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-red-600 rounded-xl flex items-center justify-center">
                <Shield className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">
                  True911 <span className="text-red-500">Command</span>
                </h1>
                <p className="text-xs text-slate-500">
                  Life-safety command center &middot; {user?.name}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowScenario(s => !s)}
                className="flex items-center gap-1.5 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium transition-colors border border-slate-700/50"
              >
                <Zap className="w-3.5 h-3.5 text-amber-500" />
                {showScenario ? "Hide Scenario" : "Run Scenario"}
              </button>
              <span className="text-xs text-slate-600 hidden sm:block">
                {timeSince(lastRefresh.toISOString())}
              </span>
              <button onClick={fetchData} className="p-2 rounded-lg border border-slate-700/50 hover:bg-slate-800 text-slate-500">
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* KPI strip */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <KPICard
              label="Sites Monitored"
              value={p.total_sites}
              icon={Building2}
              color="bg-slate-800 text-slate-400"
              sub={`${p.connected_sites} connected`}
            />
            <KPICard
              label="Active Incidents"
              value={data?.active_incidents || 0}
              icon={AlertOctagon}
              color="bg-red-900/40 text-red-400"
              border={data?.critical_incidents > 0 ? "border-red-700/50" : "border-slate-700/50"}
              sub={data?.critical_incidents > 0 ? `${data.critical_incidents} critical` : "All clear"}
            />
            <KPICard
              label="Needs Attention"
              value={p.attention_sites}
              icon={Eye}
              color="bg-amber-900/30 text-amber-400"
              sub="Sites with warnings"
            />
            <KPICard
              label="Active Devices"
              value={p.active_devices}
              icon={Cpu}
              color="bg-blue-900/30 text-blue-400"
              sub={`${p.total_devices} total`}
            />
            <KPICard
              label="Readiness"
              value={`${readiness.score || 0}%`}
              icon={Activity}
              color={readiness.score >= 85 ? "bg-emerald-900/30 text-emerald-400" : readiness.score >= 60 ? "bg-amber-900/30 text-amber-400" : "bg-red-900/30 text-red-400"}
              border={readiness.score < 60 ? "border-red-700/50" : "border-slate-700/50"}
              sub={readiness.risk_label}
            />
          </div>

          {/* Scenario runner */}
          {showScenario && <ScenarioRunner onRefresh={fetchData} />}

          {/* Main grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Left 2/3 */}
            <div className="lg:col-span-2 space-y-5">
              <IncidentFeed
                incidents={incidents}
                onRefresh={fetchData}
                onSelectSite={(siteId) => {
                  window.location.href = createPageUrl("CommandSite") + `?site=${siteId}`;
                }}
              />

              <SystemHealthMatrix systems={systemHealth} />

              {/* Activity timeline */}
              <ActivityTimeline activities={activities} />
            </div>

            {/* Right 1/3 */}
            <div className="space-y-5">
              <ReadinessScore readiness={readiness} />

              {/* Sites needing attention */}
              <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
                <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700/50">
                  <h3 className="text-sm font-semibold text-white">Sites Needing Attention</h3>
                  <Link
                    to={createPageUrl("Sites")}
                    className="text-xs text-red-500 hover:text-red-400 font-medium flex items-center gap-0.5"
                  >
                    All Sites <ChevronRight className="w-3 h-3" />
                  </Link>
                </div>
                <div className="divide-y divide-slate-800/50 max-h-[300px] overflow-y-auto">
                  {attentionSites.length === 0 && (
                    <div className="px-5 py-8 text-center text-sm text-slate-600">All sites operational</div>
                  )}
                  {attentionSites.map((site) => (
                    <Link
                      key={site.site_id}
                      to={createPageUrl("CommandSite") + `?site=${site.site_id}`}
                      className="flex items-center justify-between px-5 py-3 hover:bg-slate-800/50 transition-colors"
                    >
                      <div>
                        <p className="text-sm text-slate-200">{site.site_name}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className={`w-1.5 h-1.5 rounded-full ${
                            site.status === "Not Connected" ? "bg-red-500" : "bg-amber-500"
                          }`} />
                          <span className="text-xs text-slate-500">{site.status}</span>
                          {site.kit_type && (
                            <span className="text-xs text-slate-600">{site.kit_type}</span>
                          )}
                        </div>
                      </div>
                      <ChevronRight className="w-4 h-4 text-slate-600" />
                    </Link>
                  ))}
                </div>
              </div>

              {/* Quick actions */}
              <div className="bg-slate-900 rounded-xl border border-slate-700/50 p-5">
                <h3 className="text-sm font-semibold text-white mb-3">Quick Actions</h3>
                <div className="space-y-2">
                  <Link
                    to={createPageUrl("Incidents")}
                    className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg bg-slate-800/50 hover:bg-slate-800 text-slate-300 text-sm transition-colors"
                  >
                    <AlertOctagon className="w-4 h-4 text-red-500" />
                    View All Incidents
                  </Link>
                  <Link
                    to={createPageUrl("DeploymentMap")}
                    className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg bg-slate-800/50 hover:bg-slate-800 text-slate-300 text-sm transition-colors"
                  >
                    <Radio className="w-4 h-4 text-blue-500" />
                    Deployment Map
                  </Link>
                  <Link
                    to={createPageUrl("Reports")}
                    className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg bg-slate-800/50 hover:bg-slate-800 text-slate-300 text-sm transition-colors"
                  >
                    <Activity className="w-4 h-4 text-emerald-500" />
                    Generate Report
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </PageWrapper>
  );
}
