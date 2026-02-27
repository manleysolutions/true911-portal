import { useState, useEffect, useCallback } from "react";
import { Device, Site } from "@/api/entities";
import { apiFetch } from "@/api/client";
import { Cpu, RefreshCw, Search, Plus, X, CheckCircle2, Radio, KeyRound, Copy, Check } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import SiteDrawer from "@/components/SiteDrawer";
import ComputedStatusBadge from "@/components/ui/ComputedStatusBadge";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

function timeSince(iso) {
  if (!iso) return "\u2014";
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

/* ── One-time API key display modal ── */
function ApiKeyModal({ deviceId, apiKey, onClose }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(apiKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-[70] bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6" onClick={e => e.stopPropagation()}>
        <div className="text-center mb-4">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-amber-100 rounded-full mb-3">
            <KeyRound className="w-6 h-6 text-amber-600" />
          </div>
          <h3 className="text-lg font-bold text-gray-900">Device API Key</h3>
          <p className="text-sm text-gray-500 mt-1">
            Device <span className="font-mono font-semibold">{deviceId}</span>
          </p>
        </div>

        <div className="bg-red-50 border border-red-200 rounded-xl p-3 mb-4">
          <p className="text-xs font-semibold text-red-700 text-center">
            Copy this key now — it will not be shown again.
          </p>
        </div>

        <div className="relative mb-5">
          <div className="bg-gray-900 text-emerald-400 font-mono text-xs p-4 rounded-xl break-all select-all leading-relaxed">
            {apiKey}
          </div>
          <button
            onClick={handleCopy}
            className="absolute top-2 right-2 p-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
            title="Copy to clipboard"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>

        <div className="bg-gray-50 rounded-xl p-3 mb-5 text-xs text-gray-600 space-y-1.5">
          <div className="font-semibold text-gray-700 uppercase tracking-wide text-[10px]">Usage</div>
          <div className="font-mono text-[11px] bg-white border border-gray-200 rounded-lg p-2.5 leading-relaxed">
            curl -X POST {window.location.origin}/api/heartbeat \<br />
            {"  "}-H "X-Device-Key: {apiKey.slice(0, 12)}..." \<br />
            {"  "}-H "Content-Type: application/json" \<br />
            {"  "}-d '{`{"device_id":"${deviceId}"}`}'
          </div>
        </div>

        <button
          onClick={onClose}
          className="w-full bg-gray-900 hover:bg-gray-800 text-white font-semibold py-2.5 px-4 rounded-xl text-sm"
        >
          I've saved the key
        </button>
      </div>
    </div>
  );
}

/* ── PR12 registration modal ── */
function RegisterPR12Modal({ onClose, onCreated, sites }) {
  const [form, setForm] = useState({
    device_id: "",
    imei: "",
    iccid: "",
    msisdn: "",
    site_id: "",
    serial_number: "",
    notes: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(null);

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      const result = await Device.create({
        device_id: form.device_id,
        imei: form.imei || undefined,
        iccid: form.iccid || undefined,
        msisdn: form.msisdn || undefined,
        site_id: form.site_id || undefined,
        serial_number: form.serial_number || undefined,
        notes: form.notes || undefined,
        device_type: "PR12",
        model: "PR12",
        status: "provisioning",
      });
      setCreated(result);
      onCreated();
    } catch (err) {
      setError(err?.message || "Failed to register device.");
      setSaving(false);
    }
  };

  if (created) {
    return (
      <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
        <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6" onClick={e => e.stopPropagation()}>
          <div className="text-center mb-5">
            <div className="inline-flex items-center justify-center w-12 h-12 bg-emerald-100 rounded-full mb-3">
              <CheckCircle2 className="w-6 h-6 text-emerald-600" />
            </div>
            <h3 className="text-lg font-bold text-gray-900">PR12 Registered</h3>
            <p className="text-sm text-gray-500 mt-1">Device <span className="font-mono font-semibold">{created.device_id}</span> created in provisioning status.</p>
          </div>

          {created.api_key && (
            <div className="mb-5">
              <div className="bg-red-50 border border-red-200 rounded-xl p-3 mb-3">
                <p className="text-xs font-semibold text-red-700 text-center">
                  Copy the device API key now — it will not be shown again.
                </p>
              </div>
              <div className="bg-gray-900 text-emerald-400 font-mono text-xs p-3 rounded-xl break-all select-all leading-relaxed">
                {created.api_key}
              </div>
            </div>
          )}

          <div className="bg-gray-50 rounded-xl p-4 mb-5 space-y-2 text-sm">
            <div className="font-semibold text-gray-700 text-xs uppercase tracking-wide mb-2">Next Steps</div>
            <div className="flex items-start gap-2">
              <span className="w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-bold flex-shrink-0 mt-0.5">1</span>
              <span className="text-gray-600">Insert SIM card and power on the PR12 device.</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-bold flex-shrink-0 mt-0.5">2</span>
              <span className="text-gray-600">Configure the device with the API key shown above.</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-bold flex-shrink-0 mt-0.5">3</span>
              <span className="text-gray-600">Activate SIM with carrier using ICCID{created.iccid ? ` (${created.iccid})` : ""}.</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] flex items-center justify-center font-bold flex-shrink-0 mt-0.5">4</span>
              <span className="text-gray-600">Wait for first heartbeat — live status will change to <span className="font-semibold text-emerald-700">Online</span>.</span>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-full bg-gray-900 hover:bg-gray-800 text-white font-semibold py-2.5 px-4 rounded-xl text-sm"
          >
            Done
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 pt-5 pb-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-red-600" />
            <h3 className="text-base font-bold text-gray-900">Register PR12 Device</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Device ID *</label>
            <input
              value={form.device_id}
              onChange={set("device_id")}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
              placeholder="e.g. PR12-001"
              required
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">IMEI</label>
              <input
                value={form.imei}
                onChange={set("imei")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="15-digit IMEI"
                maxLength={15}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">ICCID</label>
              <input
                value={form.iccid}
                onChange={set("iccid")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="SIM ICCID"
                maxLength={22}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">MSISDN</label>
              <input
                value={form.msisdn}
                onChange={set("msisdn")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="Phone number"
                maxLength={15}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Serial Number</label>
              <input
                value={form.serial_number}
                onChange={set("serial_number")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="Board serial"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Assign to Site</label>
              <select
                value={form.site_id}
                onChange={set("site_id")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
              >
                <option value="">— No site yet —</option>
                {sites.map(s => (
                  <option key={s.site_id} value={s.site_id}>{s.site_name} ({s.site_id})</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Notes</label>
            <textarea
              value={form.notes}
              onChange={set("notes")}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent resize-none"
              rows={2}
              placeholder="Optional install notes..."
            />
          </div>

          {error && (
            <div className="bg-red-50 border border-red-100 text-red-600 text-xs px-4 py-3 rounded-xl">{error}</div>
          )}

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-2.5 px-4 rounded-xl text-sm">
              Cancel
            </button>
            <button type="submit" disabled={saving} className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-2.5 px-4 rounded-xl text-sm">
              {saving ? "Registering..." : "Register PR12"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ── Main Devices page ── */
export default function Devices() {
  const { can } = useAuth();
  const [devices, setDevices] = useState([]);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedSite, setSelectedSite] = useState(null);
  const [showRegister, setShowRegister] = useState(false);
  const [rotateKeyResult, setRotateKeyResult] = useState(null);

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

  const handleRotateKey = async (device) => {
    try {
      const result = await apiFetch(`/devices/${device.id}/rotate-key`, { method: "POST" });
      setRotateKeyResult(result);
    } catch (err) {
      toast.error(err?.message || "Failed to rotate key.");
    }
  };

  const filtered = devices.filter(d => {
    if (statusFilter && d.status !== statusFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      const site = siteMap[d.site_id];
      return (
        d.device_id.toLowerCase().includes(q) ||
        (d.serial_number || "").toLowerCase().includes(q) ||
        (d.model || "").toLowerCase().includes(q) ||
        (d.imei || "").toLowerCase().includes(q) ||
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
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowRegister(true)}
              className="flex items-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold transition-colors"
            >
              <Plus className="w-4 h-4" /> Register PR12
            </button>
            <button onClick={fetchData} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search devices, serial, IMEI, model, site..."
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
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">IMEI</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Serial</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Status</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Live</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Last Heartbeat</th>
                {can("ROTATE_DEVICE_KEY") && (
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase w-10"></th>
                )}
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
                    <td className="px-4 py-2.5 text-gray-800">{site?.site_name || d.site_id || "\u2014"}</td>
                    <td className="px-4 py-2.5 text-gray-600">{d.model || "\u2014"}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{d.imei || "\u2014"}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{d.serial_number || "\u2014"}</td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_BADGE[d.status] || STATUS_BADGE.inactive}`}>
                        {d.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <ComputedStatusBadge status={d.computed_status} />
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-500">{timeSince(d.last_heartbeat)}</td>
                    {can("ROTATE_DEVICE_KEY") && (
                      <td className="px-4 py-2.5" onClick={e => e.stopPropagation()}>
                        {d.has_api_key && (
                          <button
                            onClick={() => handleRotateKey(d)}
                            className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
                            title="Rotate API key"
                          >
                            <KeyRound className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={can("ROTATE_DEVICE_KEY") ? 9 : 8} className="px-4 py-8 text-center text-sm text-gray-400">No devices found</td>
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

      {showRegister && (
        <RegisterPR12Modal
          sites={sites}
          onClose={() => setShowRegister(false)}
          onCreated={fetchData}
        />
      )}

      {rotateKeyResult && (
        <ApiKeyModal
          deviceId={rotateKeyResult.device_id}
          apiKey={rotateKeyResult.api_key}
          onClose={() => setRotateKeyResult(null)}
        />
      )}
    </PageWrapper>
  );
}
