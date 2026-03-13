import { useState, useEffect, useCallback } from "react";
import { Device, Site, HardwareModel } from "@/api/entities";
import { apiFetch } from "@/api/client";
import { Cpu, RefreshCw, Search, Plus, X, CheckCircle2, Radio, KeyRound, Copy, Check, Pencil, Trash2, Loader2, Link2, Unlink } from "lucide-react";
import PageWrapper from "@/components/PageWrapper";
import SiteDrawer from "@/components/SiteDrawer";
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

/* ── Identity type helpers ── */
const STARLINK_MODELS = new Set(["napco-slelte", "napco-sle5g"]);
const ATA_MODELS = new Set(["cisco-ata191", "cisco-ata192"]);
const CARRIER_OPTIONS_DEV = ["Verizon", "AT&T", "T-Mobile", "Telnyx"];

function identityTypeForModel(hwModelId) {
  if (STARLINK_MODELS.has(hwModelId)) return "starlink";
  if (ATA_MODELS.has(hwModelId)) return "ata";
  if (hwModelId) return "cellular";
  return "";
}

/* ── Assigned SIMs panel (shown inside edit modal) ── */
function DeviceSimPanel({ deviceId }) {
  const { can } = useAuth();
  const [sims, setSims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [unassigning, setUnassigning] = useState(null);
  const [showPicker, setShowPicker] = useState(false);
  const [availableSims, setAvailableSims] = useState([]);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [selectedSimId, setSelectedSimId] = useState("");

  const fetchSims = useCallback(async () => {
    try {
      const data = await apiFetch(`/devices/${deviceId}/sims`);
      setSims(data);
    } catch { /* silently fail — endpoint may not exist yet */ }
    setLoading(false);
  }, [deviceId]);

  useEffect(() => { fetchSims(); }, [fetchSims]);

  const handleUnassign = async (simId) => {
    setUnassigning(simId);
    try {
      await apiFetch(`/sims/${simId}/unassign`, { method: "POST" });
      toast.success("SIM unassigned");
      fetchSims();
    } catch (err) {
      toast.error(err?.message || "Failed to unassign SIM");
    }
    setUnassigning(null);
  };

  const handleOpenPicker = async () => {
    setShowPicker(true);
    setPickerLoading(true);
    try {
      const data = await apiFetch("/sims?unassigned=true&limit=200");
      setAvailableSims(data);
    } catch {
      setAvailableSims([]);
    }
    setPickerLoading(false);
  };

  const handleAssign = async () => {
    if (!selectedSimId) return;
    setAssigning(true);
    try {
      await apiFetch(`/sims/${selectedSimId}/assign`, {
        method: "POST",
        body: JSON.stringify({ device_id: deviceId, slot: 1 }),
      });
      toast.success("SIM assigned to device");
      setShowPicker(false);
      setSelectedSimId("");
      fetchSims();
    } catch (err) {
      toast.error(err?.message || "Failed to assign SIM");
    }
    setAssigning(false);
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-gray-400 py-2">
        <Loader2 className="w-3 h-3 animate-spin" /> Loading SIMs...
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {sims.map(s => (
        <div key={s.id} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
          <div className="flex-1 min-w-0">
            <div className="font-mono text-xs text-gray-700 truncate">{s.iccid}</div>
            <div className="text-[10px] text-gray-500">
              {s.carrier} {s.msisdn ? `| ${s.msisdn}` : ""} | {s.status}
            </div>
          </div>
          <button
            onClick={() => handleUnassign(s.id)}
            disabled={unassigning === s.id}
            className="ml-2 p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 transition-colors"
            title="Unassign SIM"
          >
            {unassigning === s.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Unlink className="w-3.5 h-3.5" />}
          </button>
        </div>
      ))}

      {sims.length === 0 && !showPicker && (
        <div className="text-xs text-gray-400 py-1">No SIMs assigned to this device.</div>
      )}

      {/* SIM Assign Picker */}
      {can("MANAGE_SIMS") && !showPicker && (
        <button
          onClick={handleOpenPicker}
          className="flex items-center gap-1.5 text-xs text-red-600 hover:text-red-700 font-medium mt-1"
        >
          <Link2 className="w-3 h-3" /> Link SIM
        </button>
      )}

      {showPicker && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 space-y-2">
          <div className="text-xs font-semibold text-gray-700">Assign a SIM</div>
          {pickerLoading ? (
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <Loader2 className="w-3 h-3 animate-spin" /> Loading available SIMs...
            </div>
          ) : availableSims.length === 0 ? (
            <div className="text-xs text-gray-400">No unassigned SIMs available.</div>
          ) : (
            <select
              value={selectedSimId}
              onChange={e => setSelectedSimId(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-red-500"
            >
              <option value="">-- Select a SIM --</option>
              {availableSims.map(s => (
                <option key={s.id} value={s.id}>
                  {s.iccid} ({s.carrier}{s.msisdn ? ` | ${s.msisdn}` : ""})
                </option>
              ))}
            </select>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => { setShowPicker(false); setSelectedSimId(""); }}
              className="px-3 py-1.5 text-xs text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={handleAssign}
              disabled={!selectedSimId || assigning}
              className="px-3 py-1.5 text-xs text-white bg-red-600 hover:bg-red-700 disabled:bg-red-300 rounded-lg font-medium"
            >
              {assigning ? "Assigning..." : "Assign"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Device form modal (create or edit) ── */
function DeviceFormModal({ onClose, onSaved, sites, hardwareModels, editDevice }) {
  const isEdit = !!editDevice;
  const [form, setForm] = useState({
    device_id: editDevice?.device_id || "",
    imei: editDevice?.imei || "",
    iccid: editDevice?.iccid || "",
    msisdn: editDevice?.msisdn || "",
    carrier: editDevice?.carrier || "",
    site_id: editDevice?.site_id || "",
    serial_number: editDevice?.serial_number || "",
    mac_address: editDevice?.mac_address || "",
    starlink_id: editDevice?.starlink_id || "",
    hardware_model_id: editDevice?.hardware_model_id || "",
    device_type: editDevice?.device_type || "",
    model: editDevice?.model || "",
    identifier_type: editDevice?.identifier_type || "",
    notes: editDevice?.notes || "",
    status: editDevice?.status || "provisioning",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(null);

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }));

  // Derive identity type from selected hardware model
  const idType = form.identifier_type || identityTypeForModel(form.hardware_model_id);
  const isCellular = idType === "cellular" || idType === "";
  const isStarlink = idType === "starlink";
  const isAta = idType === "ata";

  // Group hardware models by manufacturer
  const mfrs = [...new Set(hardwareModels.map(m => m.manufacturer))].sort();

  const handleModelChange = (e) => {
    const id = e.target.value;
    const hm = hardwareModels.find(m => m.id === id);
    const newIdType = identityTypeForModel(id);
    setForm(f => ({
      ...f,
      hardware_model_id: id,
      device_type: hm?.device_type || f.device_type,
      model: hm?.model_name || f.model,
      identifier_type: newIdType,
      // Clear fields that don't apply to the new type
      ...(newIdType === "starlink" ? { imei: "", iccid: "", msisdn: "", carrier: "" } : {}),
      ...(newIdType === "ata" ? { imei: "", iccid: "", msisdn: "", carrier: "", starlink_id: "" } : {}),
      ...(newIdType === "cellular" ? { starlink_id: "" } : {}),
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    // Validate required fields per identity type
    if (isStarlink && !form.starlink_id.trim()) {
      setError("StarLink ID is required for Napco devices.");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        device_id: form.device_id,
        site_id: form.site_id || undefined,
        hardware_model_id: form.hardware_model_id || undefined,
        device_type: form.device_type || "Other",
        model: form.model || form.device_type,
        identifier_type: idType || undefined,
        serial_number: form.serial_number || undefined,
        mac_address: form.mac_address || undefined,
        notes: form.notes || undefined,
        // Cellular fields
        ...(isCellular ? {
          imei: form.imei || undefined,
          iccid: form.iccid || undefined,
          msisdn: form.msisdn || undefined,
          carrier: form.carrier || undefined,
        } : {}),
        // StarLink fields
        ...(isStarlink ? {
          starlink_id: form.starlink_id || undefined,
        } : {}),
      };

      if (isEdit) {
        await Device.update(editDevice.id, { ...payload, status: form.status });
        toast.success(`Device ${form.device_id} updated`);
        onSaved();
        onClose();
      } else {
        const result = await Device.create({ ...payload, status: "provisioning" });
        setCreated(result);
        onSaved();
      }
    } catch (err) {
      const msg = err?.message || "Failed to save device.";
      setError(msg);
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
            <h3 className="text-lg font-bold text-gray-900">Device Registered</h3>
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
            <h3 className="text-base font-bold text-gray-900">{isEdit ? "Edit Device" : "Register Device"}</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Device ID + Hardware Model */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Device ID *</label>
              <input
                value={form.device_id}
                onChange={set("device_id")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="e.g. PR12-001"
                required
                disabled={isEdit}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Hardware Model *</label>
              <select
                value={form.hardware_model_id}
                onChange={handleModelChange}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
              >
                <option value="">-- Select model --</option>
                {mfrs.map(mfr => (
                  <optgroup key={mfr} label={mfr}>
                    {hardwareModels.filter(m => m.manufacturer === mfr).map(m => (
                      <option key={m.id} value={m.id}>{m.model_name}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
          </div>

          {/* Identity type hint */}
          {idType && (
            <div className="text-xs text-gray-500 bg-gray-50 px-3 py-2 rounded-lg">
              {isStarlink && "Napco StarLink device — StarLink ID required. No SIM or IMEI needed."}
              {isAta && "ATA / appliance device — Serial and MAC fields shown. No SIM or IMEI needed."}
              {isCellular && "Cellular device — IMEI, SIM ICCID, and carrier fields shown."}
            </div>
          )}

          {/* ── Cellular fields (IMEI / SIM / MSISDN / Carrier) ── */}
          {isCellular && (
            <>
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
                  <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">SIM ICCID</label>
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
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Carrier</label>
                <select
                  value={form.carrier}
                  onChange={set("carrier")}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                >
                  <option value="">-- Select carrier --</option>
                  {CARRIER_OPTIONS_DEV.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </>
          )}

          {/* ── StarLink fields ── */}
          {isStarlink && (
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">StarLink ID *</label>
              <input
                value={form.starlink_id}
                onChange={set("starlink_id")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="Napco StarLink panel ID"
                required
              />
            </div>
          )}

          {/* ── Common fields: serial, MAC, site ── */}
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
            {(isAta || isStarlink || !idType) && (
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">MAC Address</label>
                <input
                  value={form.mac_address}
                  onChange={set("mac_address")}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                  placeholder="AA:BB:CC:DD:EE:FF"
                  maxLength={17}
                />
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Assign to Site</label>
            <select
              value={form.site_id}
              onChange={set("site_id")}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
            >
              <option value="">-- Select site --</option>
              {sites.map(s => (
                <option key={s.site_id} value={s.site_id}>{s.site_name} ({s.site_id})</option>
              ))}
            </select>
          </div>

          {isEdit && (
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Status</label>
              <select
                value={form.status}
                onChange={set("status")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
              >
                <option value="provisioning">Provisioning</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="decommissioned">Decommissioned</option>
              </select>
            </div>
          )}

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

          {/* Assigned SIMs (edit mode only) */}
          {isEdit && (
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">
                <span className="flex items-center gap-1"><Link2 className="w-3 h-3" /> Assigned SIMs</span>
              </label>
              <DeviceSimPanel deviceId={editDevice.id} />
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-100 text-red-600 text-xs px-4 py-3 rounded-xl">{error}</div>
          )}

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-2.5 px-4 rounded-xl text-sm">
              Cancel
            </button>
            <button type="submit" disabled={saving} className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-semibold py-2.5 px-4 rounded-xl text-sm">
              {saving ? "Saving..." : isEdit ? "Save Changes" : "Register Device"}
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
  const [hardwareModels, setHardwareModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedSite, setSelectedSite] = useState(null);
  const [showRegister, setShowRegister] = useState(false);
  const [editDevice, setEditDevice] = useState(null);
  const [deleteDevice, setDeleteDevice] = useState(null);
  const [rotateKeyResult, setRotateKeyResult] = useState(null);

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
            <button
              onClick={() => setShowRegister(true)}
              className="flex items-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold transition-colors"
            >
              <Plus className="w-4 h-4" /> Register Device
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
                // Build identifier cell based on device type
                let idLabel = null;
                if (d.starlink_id) {
                  idLabel = <><span className="text-[10px] text-gray-400 uppercase">SL </span>{d.starlink_id}</>;
                } else if (d.imei) {
                  idLabel = <><span className="text-[10px] text-gray-400 uppercase">IMEI </span>{d.imei}</>;
                } else if (d.iccid) {
                  idLabel = <><span className="text-[10px] text-gray-400 uppercase">ICCID </span>{d.iccid}</>;
                } else if (d.mac_address) {
                  idLabel = <><span className="text-[10px] text-gray-400 uppercase">MAC </span>{d.mac_address}</>;
                }

                return (
                  <tr
                    key={d.id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => site && setSelectedSite(site)}
                  >
                    <td className="px-4 py-2.5">
                      <div className="font-mono text-xs text-gray-600">{d.device_id}</div>
                      <div className="text-[10px] text-gray-400">{d.device_type}</div>
                    </td>
                    <td className="px-4 py-2.5 text-gray-800">{site?.site_name || d.site_id || "\u2014"}</td>
                    <td className="px-4 py-2.5 text-gray-600 text-xs">{d.model || "\u2014"}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{d.serial_number || "\u2014"}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{idLabel || "\u2014"}</td>
                    <td className="px-4 py-2.5 text-gray-500 text-xs">{d.carrier || "\u2014"}</td>
                    <td className="px-4 py-2.5">
                      <HealthBadge health={d.health_status} signal={d.signal_dbm} networkStatus={d.network_status} source={d.telemetry_source} />
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_BADGE[d.status] || STATUS_BADGE.inactive}`}>
                        {d.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-500">{d.last_heartbeat ? timeSince(d.last_heartbeat) : "Awaiting"}</td>
                    <td className="px-4 py-2.5" onClick={e => e.stopPropagation()}>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => setEditDevice(d)}
                          className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-blue-600"
                          title="Edit device"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        {d.status !== "decommissioned" && (
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
        />
      )}

      {editDevice && (
        <DeviceFormModal
          sites={sites}
          hardwareModels={hardwareModels}
          editDevice={editDevice}
          onClose={() => setEditDevice(null)}
          onSaved={fetchData}
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
