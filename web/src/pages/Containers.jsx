import { useState, useEffect, useCallback, useMemo } from "react";
import { Site } from "@/api/entities";
import { Box, RefreshCw, RotateCcw, Download, GitBranch, Search, Cpu, MemoryStick, HardDrive, Activity, CheckCircle, AlertTriangle, XCircle, ChevronDown } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import { useAuth } from "@/contexts/AuthContext";
import { restartContainer, pullContainerLogs, switchChannel } from "@/components/actions";
import { toast } from "sonner";

// Simulated per-site container data (deterministic by site_id)
function getContainerData(site) {
  const hash = site.site_id.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
  const versions = ['v1.4.2', 'v1.4.3', 'v1.5.0-beta', 'v1.4.1'];
  const channels = ['stable', 'stable', 'stable', 'beta'];
  const licenseStates = ['active', 'active', 'active', 'active', 'expiring_soon', 'expired'];
  const uptimes = [99.8, 99.1, 97.4, 88.2, 72.0, 100.0];
  const cpus = [12, 18, 44, 67, 23, 8, 31];
  const mems = [38, 51, 42, 73, 29, 61, 45];

  const idx = hash % versions.length;
  const isDown = site.status === 'Not Connected';
  const isWarning = site.status === 'Attention Needed' || site.status === 'Unknown';

  const cpu = isDown ? 0 : cpus[hash % cpus.length];
  const mem = isDown ? 0 : mems[hash % mems.length];
  const uptime = isDown ? 0 : (isWarning ? uptimes[3 + (hash % 3)] : uptimes[hash % 3]);

  const healthScore = isDown ? 0 : isWarning
    ? Math.round(40 + (hash % 25))
    : Math.round(80 + (hash % 20));

  return {
    container_version: site.container_version || versions[idx],
    channel: channels[idx],
    license_state: isDown ? 'expired' : licenseStates[hash % licenseStates.length],
    uptime,
    cpu,
    mem,
    healthScore,
    last_heartbeat: site.last_checkin || site.last_device_heartbeat,
  };
}

function HealthBar({ value, size = "sm" }) {
  const color = value >= 80 ? "bg-emerald-500" : value >= 50 ? "bg-amber-500" : "bg-red-500";
  const h = size === "sm" ? "h-1.5" : "h-2";
  return (
    <div className={`w-full bg-gray-100 rounded-full ${h} overflow-hidden`}>
      <div className={`${color} ${h} rounded-full transition-all`} style={{ width: `${value}%` }} />
    </div>
  );
}

function LicenseBadge({ state }) {
  const map = {
    active: "bg-emerald-50 text-emerald-700 border-emerald-200",
    expiring_soon: "bg-amber-50 text-amber-700 border-amber-200",
    expired: "bg-red-50 text-red-700 border-red-200",
  };
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded border ${map[state] || map.active}`}>
      {state?.replace('_', ' ')}
    </span>
  );
}

function ChannelBadge({ channel }) {
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded border ${
      channel === 'beta' ? 'bg-purple-50 text-purple-700 border-purple-200' : 'bg-blue-50 text-blue-700 border-blue-200'
    }`}>
      {channel}
    </span>
  );
}

function MetricPill({ icon: Icon, value, label, warn }) {
  return (
    <div className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs ${warn ? 'bg-amber-50 text-amber-700' : 'bg-gray-50 text-gray-600'}`}>
      <Icon className="w-3 h-3" />
      <span className="font-semibold">{value}%</span>
      <span className="text-[10px] opacity-70">{label}</span>
    </div>
  );
}

function timeSince(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso);
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function ContainerRow({ site, cdata, onAction }) {
  const { can } = useAuth();
  const [actionLoading, setActionLoading] = useState(null);
  const [showChannelMenu, setShowChannelMenu] = useState(false);
  const { user } = useAuth();

  const handleRestart = async () => {
    setActionLoading('restart');
    const result = await restartContainer(user, site);
    setActionLoading(null);
    toast.success(`Container restart initiated for ${site.site_name}`);
    onAction();
  };

  const handlePullLogs = async () => {
    setActionLoading('logs');
    const result = await pullContainerLogs(user, site);
    setActionLoading(null);
    const blob = new Blob([result.logContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${site.site_id}_container_logs_${new Date().toISOString().split('T')[0]}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Container logs downloaded.');
  };

  const handleSwitchChannel = async (ch) => {
    setShowChannelMenu(false);
    setActionLoading('channel');
    await switchChannel(user, site, ch);
    setActionLoading(null);
    toast.success(`Channel switched to "${ch}" for ${site.site_name}`);
    onAction();
  };

  const healthColor = cdata.healthScore >= 80 ? 'text-emerald-600' : cdata.healthScore >= 50 ? 'text-amber-600' : 'text-red-600';

  return (
    <tr className="hover:bg-gray-50 transition-colors border-b border-gray-50">
      <td className="px-5 py-3">
        <div className="font-medium text-sm text-gray-900 truncate max-w-[200px]">{site.site_name}</div>
        <div className="text-[10px] text-gray-400 font-mono">{site.site_id}</div>
      </td>
      <td className="px-3 py-3">
        <div className="text-xs font-mono text-gray-700">{cdata.container_version}</div>
      </td>
      <td className="px-3 py-3">
        <LicenseBadge state={cdata.license_state} />
      </td>
      <td className="px-3 py-3">
        <ChannelBadge channel={cdata.channel} />
      </td>
      <td className="px-3 py-3 text-xs text-gray-600">{timeSince(cdata.last_heartbeat)}</td>
      <td className="px-3 py-3">
        <div className="text-xs font-medium text-gray-700">{cdata.uptime.toFixed(1)}%</div>
        <HealthBar value={cdata.uptime} />
      </td>
      <td className="px-3 py-3">
        <div className="flex gap-1.5">
          <MetricPill icon={Cpu} value={cdata.cpu} label="CPU" warn={cdata.cpu > 60} />
          <MetricPill icon={MemoryStick} value={cdata.mem} label="MEM" warn={cdata.mem > 70} />
        </div>
      </td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-1">
          <span className={`text-sm font-bold ${healthColor}`}>{cdata.healthScore}</span>
          <span className="text-[10px] text-gray-400">/100</span>
        </div>
        <HealthBar value={cdata.healthScore} />
      </td>
      <td className="px-3 py-3">
        {can('RESTART_CONTAINER') && (
          <div className="flex items-center gap-1.5">
            <button
              onClick={handleRestart}
              disabled={!!actionLoading}
              title="Restart Container"
              className="p-1.5 rounded-lg border border-gray-200 hover:bg-amber-50 hover:border-amber-300 text-gray-500 hover:text-amber-700 transition-all disabled:opacity-40"
            >
              {actionLoading === 'restart' ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <RotateCcw className="w-3.5 h-3.5" />
              )}
            </button>
            <button
              onClick={handlePullLogs}
              disabled={!!actionLoading}
              title="Pull Logs"
              className="p-1.5 rounded-lg border border-gray-200 hover:bg-blue-50 hover:border-blue-300 text-gray-500 hover:text-blue-700 transition-all disabled:opacity-40"
            >
              {actionLoading === 'logs' ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5" />
              )}
            </button>
            <div className="relative">
              <button
                onClick={() => setShowChannelMenu(v => !v)}
                disabled={!!actionLoading}
                title="Switch Channel"
                className="p-1.5 rounded-lg border border-gray-200 hover:bg-purple-50 hover:border-purple-300 text-gray-500 hover:text-purple-700 transition-all disabled:opacity-40 flex items-center gap-0.5"
              >
                <GitBranch className="w-3.5 h-3.5" />
                <ChevronDown className="w-2.5 h-2.5" />
              </button>
              {showChannelMenu && (
                <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-20 min-w-[120px]">
                  {['stable', 'beta'].map(ch => (
                    <button
                      key={ch}
                      onClick={() => handleSwitchChannel(ch)}
                      className={`w-full text-left px-3 py-2 text-xs hover:bg-gray-50 transition-colors first:rounded-t-lg last:rounded-b-lg ${cdata.channel === ch ? 'font-semibold text-gray-900' : 'text-gray-600'}`}
                    >
                      {cdata.channel === ch && '✓ '}{ch}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </td>
    </tr>
  );
}

export default function Containers() {
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterHealth, setFilterHealth] = useState("");
  const [filterChannel, setFilterChannel] = useState("");

  const fetchData = useCallback(async () => {
    const data = await Site.list("-last_checkin", 100);
    setSites(data);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const rows = useMemo(() => {
    return sites.map(s => ({ site: s, cdata: getContainerData(s) })).filter(({ site, cdata }) => {
      if (search) {
        const q = search.toLowerCase();
        if (!site.site_name?.toLowerCase().includes(q) && !site.site_id?.toLowerCase().includes(q)) return false;
      }
      if (filterChannel && cdata.channel !== filterChannel) return false;
      if (filterHealth === 'healthy' && cdata.healthScore < 80) return false;
      if (filterHealth === 'degraded' && (cdata.healthScore >= 80 || cdata.healthScore <= 0)) return false;
      if (filterHealth === 'critical' && cdata.healthScore > 0) return false;
      return true;
    });
  }, [sites, search, filterChannel, filterHealth]);

  const kpis = useMemo(() => {
    const all = sites.map(s => getContainerData(s));
    return {
      total: all.length,
      healthy: all.filter(c => c.healthScore >= 80).length,
      degraded: all.filter(c => c.healthScore >= 40 && c.healthScore < 80).length,
      critical: all.filter(c => c.healthScore < 40).length,
      avgCpu: all.length ? Math.round(all.reduce((a, c) => a + c.cpu, 0) / all.length) : 0,
      avgMem: all.length ? Math.round(all.reduce((a, c) => a + c.mem, 0) / all.length) : 0,
      avgHealth: all.length ? Math.round(all.reduce((a, c) => a + c.healthScore, 0) / all.length) : 0,
    };
  }, [sites]);

  return (
    <PageWrapper>
      <div className="p-6 max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Containers (CSAS)</h1>
            <p className="text-sm text-gray-500 mt-0.5">Container Software Agent Status — per-device runtime health</p>
          </div>
          <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {/* KPI row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
          {[
            { label: "Total Containers", value: kpis.total, color: "text-gray-900" },
            { label: "Healthy (≥80)", value: kpis.healthy, color: "text-emerald-600" },
            { label: "Degraded", value: kpis.degraded, color: "text-amber-600" },
            { label: "Critical (<40)", value: kpis.critical, color: "text-red-600" },
            { label: "Avg Health Score", value: kpis.avgHealth, color: kpis.avgHealth >= 80 ? "text-emerald-600" : "text-amber-600" },
            { label: "Avg CPU", value: `${kpis.avgCpu}%`, color: kpis.avgCpu > 60 ? "text-amber-600" : "text-gray-700" },
            { label: "Avg MEM", value: `${kpis.avgMem}%`, color: kpis.avgMem > 70 ? "text-amber-600" : "text-gray-700" },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="text-xs text-gray-500 mb-1">{label}</div>
              <div className={`text-2xl font-bold ${color}`}>{value}</div>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-5 flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search by site name or ID..."
              className="w-full pl-8 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
            />
          </div>
          <select
            value={filterChannel}
            onChange={e => setFilterChannel(e.target.value)}
            className="pl-3 pr-8 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
          >
            <option value="">All Channels</option>
            <option value="stable">Stable</option>
            <option value="beta">Beta</option>
          </select>
          <select
            value={filterHealth}
            onChange={e => setFilterHealth(e.target.value)}
            className="pl-3 pr-8 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-red-500"
          >
            <option value="">All Health</option>
            <option value="healthy">Healthy (≥80)</option>
            <option value="degraded">Degraded (40–79)</option>
            <option value="critical">Critical (&lt;40)</option>
          </select>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100 flex items-center gap-2">
            <Box className="w-4 h-4 text-gray-400" />
            <span className="text-sm font-semibold text-gray-700">{rows.length} containers</span>
            <span className="ml-auto text-xs text-gray-400">Actions require Admin role</span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-6 h-6 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Site</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Version</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">License</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Channel</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Last Heartbeat</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Uptime</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Resources</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Health Score</th>
                    <th className="text-left px-3 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(({ site, cdata }) => (
                    <ContainerRow key={site.id} site={site} cdata={cdata} onAction={fetchData} />
                  ))}
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={9} className="text-center py-16 text-gray-400 text-sm">No containers match the current filters.</td>
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