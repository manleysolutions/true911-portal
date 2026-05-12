import { useState, useEffect, useCallback } from "react";
import { Device, Site, HardwareModel } from "@/api/entities";
import { apiFetch } from "@/api/client";
import { RefreshCw, Search, Plus, KeyRound, Copy, Check, Pencil, Trash2, Building2 } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import SiteDrawer from "@/components/SiteDrawer";
import SitePickerModal from "@/components/SitePickerModal";
import DeviceFormModal from "@/components/DeviceFormModal";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { classifyDevice, deviceClassLabel } from "@/lib/deviceClassManifest";

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

/* ── Confirm delete modal ── */
function ConfirmDeleteModal({ device, onClose, onConfirm }) {
  const [deleting, setDeleting] = useState(false);

  const handleConfirm = async () => {
    setDeleting(true);
    await onConfirm();
  };

  return (
    <div className="fixed inset-0 z-[70] bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-full p-6" onClick={e => e.stopPropagation()}>
        <div className="text-center mb-4">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-red-100 rounded-full mb-3">
            <Trash2 className="w-6 h-6 text-red-600" />
          </div>
          <h3 className="text-lg font-bold text-gray-900">Decommission Device?</h3>
          <p className="text-sm text-gray-500 mt-1">
            Device <span className="font-mono font-semibold">{device.device_id}</span> will be marked as decommissioned.
          </p>
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-2.5 px-4 rounded-xl text-sm">
            Cancel
          </button>
          <button onClick={handleConfirm} disabled={deleting} className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-2.5 px-4 rounded-xl text-sm">
            {deleting ? "Decommissioning..." : "Decommission"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* DeviceFormModal, DeviceSimPanel, and identity-type helpers live in
   web/src/components/DeviceFormModal.jsx so SiteDetail can reuse them. */


/* ── Main Devices page ── */
export default function Devices() {
  const { can } = useAuth();
  const [devices, setDevices] = useState([]);
  const [sites, setSites] = useState([]);
  const [hardwareModels, setHardwareModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedSite, setSelectedSite] = useState(null);
  const [showRegister, setShowRegister] = useState(false);
  const [editDevice, setEditDevice] = useState(null);
  const [deleteDevice, setDeleteDevice] = useState(null);
  const [rotateKeyResult, setRotateKeyResult] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [showSitePicker, setShowSitePicker] = useState(false);

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleBulkAssignSite = async (siteId) => {
    try {
      const result = await apiFetch("/devices/bulk-assign-site", {
        method: "POST",
        body: JSON.stringify({ device_ids: [...selected], site_id: siteId }),
      });
      toast.success(`${result.assigned} device(s) assigned to site`);
      setSelected(new Set());
      setShowSitePicker(false);
      fetchData();
    } catch (err) {
      toast.error(err?.message || "Failed to assign devices to site");
    }
  };

  const fetchData = useCallback(async () => {
    const [devData, siteData, hmData] = await Promise.all([
      Device.list("-created_at", 200),
      Site.list("-last_checkin", 200),
      HardwareModel.list().catch(() => []),
    ]);
    setDevices(devData);
    setSites(siteData);
    setHardwareModels(hmData);
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const refreshSites = useCallback(async () => {
    const siteData = await Site.list("-last_checkin", 200);
    setSites(siteData);
  }, []);

  const siteMap = Object.fromEntries(sites.map(s => [s.site_id, s]));

  const handleRotateKey = async (device) => {
    try {
      const result = await apiFetch(`/devices/${device.id}/rotate-key`, { method: "POST" });
      setRotateKeyResult(result);
    } catch (err) {
      toast.error(err?.message || "Failed to rotate key.");
    }
  };

  const handleDelete = async (device) => {
    try {
      await Device.delete(device.id);
      toast.success(`Device ${device.device_id} decommissioned`);
      setDeleteDevice(null);
      fetchData();
    } catch (err) {
      toast.error(err?.message || "Failed to decommission device.");
      setDeleteDevice(null);
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
        (d.device_type || "").toLowerCase().includes(q) ||
        (d.imei || "").toLowerCase().includes(q) ||
        (d.iccid || "").toLowerCase().includes(q) ||
        (d.msisdn || "").toLowerCase().includes(q) ||
        (d.carrier || "").toLowerCase().includes(q) ||
        (d.starlink_id || "").toLowerCase().includes(q) ||
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
            {can("CREATE_DEVICES") && (
              <button
                onClick={() => setShowRegister(true)}
                className="flex items-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold transition-colors"
              >
                <Plus className="w-4 h-4" /> Register Device
              </button>
            )}
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

        {/* Bulk action bar */}
        {selected.size > 0 && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-2.5 flex items-center justify-between">
            <span className="text-red-800 text-xs font-semibold">{selected.size} device(s) selected</span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowSitePicker(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold"
              >
                <Building2 className="w-3.5 h-3.5" /> Assign Selected to Site
              </button>
              <button
                onClick={() => setSelected(new Set())}
                className="px-3 py-1.5 text-xs text-gray-600 border border-gray-200 rounded-lg hover:bg-white"
              >
                Clear
              </button>
            </div>
          </div>
        )}

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-3 py-2.5 w-8">
                  <input
                    type="checkbox"
                    checked={filtered.length > 0 && selected.size === filtered.length}
                    onChange={() => {
                      if (selected.size === filtered.length) setSelected(new Set());
                      else setSelected(new Set(filtered.map(d => d.id)));
                    }}
                    className="rounded border-gray-300 text-red-600 focus:ring-red-500"
                  />
                </th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Device ID</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Site</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Model</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Serial</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Identifier</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Carrier</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Health</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Status</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase">Last HB</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase w-24">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map(d => {
                const site = siteMap[d.site_id];
                // Build identifier cell based on device class manifest.
                // Manual-verification classes (Napco / StarLink / SLELTE)
                // intentionally never surface IMEI/ICCID even if those
                // columns happen to be populated — they're noise for a
                // non-cellular endpoint.
                const manifest = classifyDevice(d);
                let idLabel = null;
                if (manifest.manualVerification) {
                  if (d.starlink_id) {
                    idLabel = <><span className="text-[10px] text-gray-400 uppercase">SL </span>{d.starlink_id}</>;
                  } else if (d.serial_number) {
                    idLabel = <><span className="text-[10px] text-gray-400 uppercase">SN </span>{d.serial_number}</>;
                  }
                } else if (d.starlink_id) {
                  idLabel = <><span className="text-[10px] text-gray-400 uppercase">SL </span>{d.starlink_id}</>;
                } else if (d.imei) {
                  idLabel = <><span className="text-[10px] text-gray-400 uppercase">IMEI </span>{d.imei}</>;
                } else if (d.iccid) {
                  idLabel = <><span className="text-[10px] text-gray-400 uppercase">ICCID </span>{d.iccid}</>;
                } else if (d.mac_address) {
                  idLabel = <><span className="text-[10px] text-gray-400 uppercase">MAC </span>{d.mac_address}</>;
                }
                const carrierLabel = manifest.manualVerification
                  ? deviceClassLabel(d)
                  : (d.carrier || "—");
                const lastHbLabel = manifest.liveTelemetry
                  ? (d.last_heartbeat ? timeSince(d.last_heartbeat) : "Awaiting")
                  : "Manual";

                return (
                  <tr
                    key={d.id}
                    className={`hover:bg-gray-50 cursor-pointer ${selected.has(d.id) ? "bg-red-50/50" : ""}`}
                    onClick={() => site && setSelectedSite(site)}
                  >
                    <td className="px-3 py-2.5" onClick={e => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selected.has(d.id)}
                        onChange={() => toggleSelect(d.id)}
                        className="rounded border-gray-300 text-red-600 focus:ring-red-500"
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="font-mono text-xs text-gray-600">{d.device_id}</div>
                      <div className="text-[10px] text-gray-400">{d.device_type}</div>
                    </td>
                    <td className="px-4 py-2.5 text-gray-800">{site?.site_name || d.site_id || "\u2014"}</td>
                    <td className="px-4 py-2.5 text-gray-600 text-xs">{d.model || "\u2014"}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{d.serial_number || "\u2014"}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{idLabel || "\u2014"}</td>
                    <td className="px-4 py-2.5 text-gray-500 text-xs">{carrierLabel}</td>
                    <td className="px-4 py-2.5">
                      {manifest.liveTelemetry ? (
                        <HealthBadge health={d.health_status} signal={d.signal_dbm} networkStatus={d.network_status} source={d.telemetry_source} />
                      ) : (
                        <span className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border bg-slate-50 text-slate-600 border-slate-200">
                          manual
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_BADGE[d.status] || STATUS_BADGE.inactive}`}>
                        {d.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-500">{lastHbLabel}</td>
                    <td className="px-4 py-2.5" onClick={e => e.stopPropagation()}>
                      <div className="flex items-center gap-1">
                        {can("EDIT_DEVICES") && (
                          <button
                            onClick={() => setEditDevice(d)}
                            className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-blue-600"
                            title="Edit device"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {can("DELETE_DEVICES") && d.status !== "decommissioned" && (
                          <button
                            onClick={() => setDeleteDevice(d)}
                            className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-red-600"
                            title="Decommission device"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {can("ROTATE_DEVICE_KEY") && d.has_api_key && (
                          <button
                            onClick={() => handleRotateKey(d)}
                            className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
                            title="Rotate API key"
                          >
                            <KeyRound className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-sm text-gray-400">No devices found</td>
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
        <DeviceFormModal
          sites={sites}
          hardwareModels={hardwareModels}
          onClose={() => setShowRegister(false)}
          onSaved={fetchData}
          onSitesRefresh={refreshSites}
        />
      )}

      {editDevice && (
        <DeviceFormModal
          sites={sites}
          hardwareModels={hardwareModels}
          editDevice={editDevice}
          onClose={() => setEditDevice(null)}
          onSaved={fetchData}
          onSitesRefresh={refreshSites}
        />
      )}

      {deleteDevice && (
        <ConfirmDeleteModal
          device={deleteDevice}
          onClose={() => setDeleteDevice(null)}
          onConfirm={() => handleDelete(deleteDevice)}
        />
      )}

      {rotateKeyResult && (
        <ApiKeyModal
          deviceId={rotateKeyResult.device_id}
          apiKey={rotateKeyResult.api_key}
          onClose={() => setRotateKeyResult(null)}
        />
      )}

      {showSitePicker && (
        <SitePickerModal
          title="Assign Devices to Site"
          count={selected.size}
          entityLabel="device(s)"
          onClose={() => setShowSitePicker(false)}
          onConfirm={handleBulkAssignSite}
        />
      )}
    </PageWrapper>
  );
}

const HEALTH_STYLES = {
  healthy:  "bg-emerald-50 text-emerald-700 border-emerald-200",
  warning:  "bg-amber-50 text-amber-700 border-amber-200",
  critical: "bg-red-50 text-red-700 border-red-200",
  unknown:  "bg-gray-100 text-gray-500 border-gray-200",
};

const HEALTH_DOT = {
  healthy: "bg-emerald-500",
  warning: "bg-amber-500",
  critical: "bg-red-500",
  unknown: "bg-gray-400",
};

const SOURCE_LABELS = {
  pr12_heartbeat: "PR12",
  inseego_heartbeat: "Inseego",
  device_heartbeat: "Device",
  verizon_carrier: "Verizon API",
  "t-mobile_carrier": "T-Mobile API",
  att_carrier: "AT&T API",
};

function HealthBadge({ health, signal, networkStatus, source }) {
  const h = health || "unknown";
  const parts = [h];
  if (signal != null) parts.push(`${signal} dBm`);
  if (networkStatus) parts.push(networkStatus);
  if (source) parts.push(`via ${SOURCE_LABELS[source] || source}`);
  const title = parts.join(" | ");

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${HEALTH_STYLES[h] || HEALTH_STYLES.unknown}`}
      title={title}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${HEALTH_DOT[h] || HEALTH_DOT.unknown}`} />
      {h}
    </span>
  );
}
