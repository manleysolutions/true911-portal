import { useState, useEffect, useCallback } from "react";
import { Device, Site } from "@/api/entities";
import { Cpu, RefreshCw, Search } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
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

const STATUS_BADGE = {
  active: "bg-emerald-50 text-emerald-700 border-emerald-200",
  provisioning: "bg-blue-50 text-blue-700 border-blue-200",
  inactive: "bg-red-50 text-red-700 border-red-200",
  decommissioned: "bg-gray-100 text-gray-500 border-gray-200",
};

export default function Devices() {
  const [devices, setDevices] = useState([]);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedSite, setSelectedSite] = useState(null);

  const fetchData = useCallback(async () => {
    const [devData, siteData] = await Promise.all([
      Device.list("-created_at", 200),
      Site.list("-last_checkin", 200),
    ]);
    setDevices(devData);
    setSites(siteData);
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const siteMap = Object.fromEntries(sites.map(s => [s.site_id, s]));

  const filtered = devices.filter(d => {
    if (statusFilter && d.status !== statusFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      const site = siteMap[d.site_id];
      return (
        d.device_id.toLowerCase().includes(q) ||
        (d.serial_number || "").toLowerCase().includes(q) ||
        (d.model || "").toLowerCase().includes(q) ||
        (site?.site_name || "").toLowerCase().includes(q)
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
            <h1 className="text-2xl font-bold text-gray-900">Devices</h1>
            <p className="text-sm text-gray-500 mt-0.5">{devices.length} devices registered</p>
          </div>
          <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search devices, serial, model, site..."
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm"
            />
          </div>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm"
          >
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="provisioning">Provisioning</option>
            <option value="inactive">Inactive</option>
            <option value="decommissioned">Decommissioned</option>
          </select>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Device ID</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Site</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Model</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Serial</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Firmware</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Status</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Last Heartbeat</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map(d => {
                const site = siteMap[d.site_id];
                return (
                  <tr
                    key={d.id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => site && setSelectedSite(site)}
                  >
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-600">{d.device_id}</td>
                    <td className="px-4 py-2.5 text-gray-800">{site?.site_name || d.site_id || "—"}</td>
                    <td className="px-4 py-2.5 text-gray-600">{d.model || "—"}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{d.serial_number || "—"}</td>
                    <td className="px-4 py-2.5 text-gray-600">{d.firmware_version || "—"}</td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_BADGE[d.status] || STATUS_BADGE.inactive}`}>
                        {d.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-500">{timeSince(d.last_heartbeat)}</td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-sm text-gray-400">No devices found</td>
                </tr>
              )}
            </tbody>
          </table>
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
