import { useState, useEffect, useCallback } from "react";
import { Site, TelemetryEvent, Device, Line, Event as EventEntity } from "@/api/entities";
import { Building2, Wifi, WifiOff, AlertTriangle, HelpCircle, RefreshCw, Bell, TrendingUp, Rocket, Cpu, Phone, Activity } from "lucide-react";
import { Link } from "react-router-dom";
import { createPageUrl } from "@/utils";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { isDemo } from "@/config";
import TriageQueue from "@/components/TriageQueue";
import SiteDrawer from "@/components/SiteDrawer";

function timeSince(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function KPICard({ label, value, icon: Icon, colorClass, borderClass, sub, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`bg-white rounded-xl border ${borderClass || "border-gray-200"} p-4 flex flex-col gap-2 text-left w-full transition-all hover:shadow-sm ${onClick ? "cursor-pointer" : ""}`}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</span>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${colorClass}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <div>
        <div className="text-3xl font-bold text-gray-900">{value ?? "—"}</div>
        {sub && <div className="text-[11px] text-gray-400 mt-0.5">{sub}</div>}
      </div>
    </button>
  );
}

const SEV_COLORS = {
  critical: "bg-red-50 border-red-200 text-red-700",
  warning: "bg-amber-50 border-amber-200 text-amber-700",
  info: "bg-blue-50 border-blue-100 text-blue-700",
};

export default function Overview() {
  const { user } = useAuth();
  const [sites, setSites] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [devices, setDevices] = useState([]);
  const [lines, setLines] = useState([]);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSite, setSelectedSite] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [triageFilter, setTriageFilter] = useState(null);

  const fetchData = useCallback(async () => {
    const [sitesData, eventsData, devData, lineData, eventData] = await Promise.all([
      Site.list("-last_checkin", 100),
      TelemetryEvent.filter({ severity: "critical" }, "-timestamp", 20),
      Device.list("-created_at", 200),
      Line.list("-created_at", 200),
      EventEntity.filter({ severity: "critical" }, "-created_at", 10),
    ]);
    setSites(sitesData);
    setAlerts(eventsData);
    setDevices(devData);
    setLines(lineData);
    setEvents(eventData);
    setLastRefresh(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const counts = {
    total: sites.length,
    connected: sites.filter(s => s.status === "Connected").length,
    attention: sites.filter(s => s.status === "Attention Needed").length,
    notConnected: sites.filter(s => s.status === "Not Connected").length,
    unknown: sites.filter(s => s.status === "Unknown").length,
  };

  const uptimePct = counts.total > 0 ? Math.round((counts.connected / counts.total) * 100) : 0;
  const siteById = Object.fromEntries(sites.map(s => [s.site_id, s]));

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
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Overview</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Welcome back, <span className="font-medium text-gray-700">{user?.name?.split(" ")[0]}</span>
              &nbsp;·&nbsp;Auto-refreshes every 30s
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400 hidden sm:block">Updated {timeSince(lastRefresh.toISOString())}</span>
            <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Demo banner */}
        {isDemo && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-2.5 flex items-center gap-2">
            <span className="text-amber-700 text-xs font-semibold">⚠ Demo Environment</span>
            <span className="text-amber-600 text-xs">— All actions are simulated. No live devices are connected.</span>
          </div>
        )}

        {/* KPI Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <KPICard
            label="Total Sites"
            value={counts.total}
            icon={Building2}
            colorClass="bg-gray-100 text-gray-600"
            borderClass="border-gray-200"
          />
          <KPICard
            label="Connected"
            value={counts.connected}
            icon={Wifi}
            colorClass="bg-emerald-100 text-emerald-700"
            borderClass="border-emerald-200"
            sub={`${uptimePct}% fleet uptime`}
          />
          <KPICard
            label="Attention Needed"
            value={counts.attention}
            icon={AlertTriangle}
            colorClass="bg-amber-100 text-amber-700"
            borderClass="border-amber-200"
            onClick={() => setTriageFilter(f => f === "Attention Needed" ? null : "Attention Needed")}
            sub="Click to filter"
          />
          <KPICard
            label="Not Connected"
            value={counts.notConnected}
            icon={WifiOff}
            colorClass="bg-red-100 text-red-700"
            borderClass="border-red-200"
            onClick={() => setTriageFilter(f => f === "Not Connected" ? null : "Not Connected")}
            sub="Click to filter"
          />
          <KPICard
            label="Unknown"
            value={counts.unknown}
            icon={HelpCircle}
            colorClass="bg-gray-200 text-gray-600"
            borderClass="border-gray-200"
            onClick={() => setTriageFilter(f => f === "Unknown" ? null : "Unknown")}
            sub="Click to filter"
          />
        </div>

        {/* Secondary KPIs */}
        <div className="grid grid-cols-3 gap-3">
          <KPICard label="Devices" value={devices.length} icon={Cpu}
            colorClass="bg-blue-100 text-blue-700" borderClass="border-blue-200"
            sub={`${devices.filter(d => d.status === "active").length} active`} />
          <KPICard label="Voice Lines" value={lines.length} icon={Phone}
            colorClass="bg-purple-100 text-purple-700" borderClass="border-purple-200"
            sub={`${lines.filter(l => l.status === "active").length} active`} />
          <KPICard label="Critical Events" value={events.length} icon={Activity}
            colorClass="bg-red-100 text-red-700" borderClass="border-red-200"
            sub="Last 24h" />
        </div>

        {/* Getting Started — shown when fleet is empty */}
        {sites.length === 0 && devices.length === 0 && (
          <div className="bg-white rounded-xl border-2 border-dashed border-red-200 p-6">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-xl bg-red-100 flex items-center justify-center flex-shrink-0">
                <Rocket className="w-5 h-5 text-red-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-base font-bold text-gray-900">Getting Started</h3>
                <p className="text-sm text-gray-500 mt-1">
                  Your fleet is empty. Set up your first site, device, and voice line using the onboarding wizard.
                </p>
                <div className="flex gap-3 mt-4">
                  <Link to={createPageUrl("OnboardingWizard")}
                    className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold transition-colors">
                    <Rocket className="w-4 h-4" /> Start Onboarding
                  </Link>
                  <Link to={createPageUrl("Sites")}
                    className="inline-flex items-center gap-1.5 px-4 py-2 border border-gray-200 hover:bg-gray-50 text-gray-700 rounded-lg text-sm font-medium transition-colors">
                    <Building2 className="w-4 h-4" /> Add Site Manually
                  </Link>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Triage Queue + Alerts */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Triage Queue — 2/3 width */}
          <div className="lg:col-span-2">
            <TriageQueue sites={sites} onOpenSite={setSelectedSite} defaultTab={triageFilter} />
          </div>

          {/* Right column */}
          <div className="flex flex-col gap-5">
            {/* Fleet Health */}
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp className="w-4 h-4 text-blue-600" />
                <h3 className="text-sm font-semibold text-gray-900">Fleet Health</h3>
              </div>
              <div className="space-y-2.5">
                {[
                  { label: "Connected", value: counts.connected, total: counts.total, color: "bg-emerald-500" },
                  { label: "Attention Needed", value: counts.attention, total: counts.total, color: "bg-amber-400" },
                  { label: "Not Connected", value: counts.notConnected, total: counts.total, color: "bg-red-500" },
                  { label: "Unknown", value: counts.unknown, total: counts.total, color: "bg-gray-300" },
                ].map(({ label, value, total, color }) => (
                  <div key={label}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-gray-600">{label}</span>
                      <span className="font-semibold text-gray-800">{value}</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                      <div
                        className={`${color} h-1.5 rounded-full transition-all`}
                        style={{ width: total > 0 ? `${(value / total) * 100}%` : "0%" }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 pt-3 border-t border-gray-100 flex items-center justify-between">
                <span className="text-xs text-gray-500">Fleet uptime</span>
                <span className={`text-lg font-bold ${uptimePct >= 90 ? "text-emerald-600" : uptimePct >= 75 ? "text-amber-600" : "text-red-600"}`}>
                  {uptimePct}%
                </span>
              </div>
            </div>

            {/* Recent Alerts */}
            <div className="bg-white rounded-xl border border-gray-200 flex flex-col min-h-0">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
                <Bell className="w-4 h-4 text-red-600" />
                <h3 className="text-sm font-semibold text-gray-900">Recent Alerts</h3>
                <span className="ml-auto bg-red-100 text-red-700 text-[10px] font-bold px-2 py-0.5 rounded-full">{alerts.length}</span>
              </div>
              <div className="overflow-y-auto max-h-[300px] divide-y divide-gray-50">
                {alerts.slice(0, 10).map(ev => {
                  const site = siteById[ev.site_id];
                  return (
                    <div
                      key={ev.id}
                      className="px-4 py-2.5 hover:bg-gray-50 cursor-pointer"
                      onClick={() => site && setSelectedSite(site)}
                    >
                      <div className={`inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded border mb-1 ${SEV_COLORS[ev.severity] || ""}`}>
                        {ev.severity}
                      </div>
                      <div className="text-xs text-gray-800 leading-tight">{ev.message}</div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[10px] text-gray-400">{site?.site_name || ev.site_id}</span>
                        <span className="text-[10px] text-gray-400 ml-auto">{timeSince(ev.timestamp)}</span>
                      </div>
                    </div>
                  );
                })}
                {alerts.length === 0 && (
                  <div className="px-4 py-8 text-center text-sm text-gray-400">No active alerts</div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <SiteDrawer
        site={selectedSite}
        onClose={() => setSelectedSite(null)}
        onSiteUpdated={fetchData}
      />
    </PageWrapper>
  );
}