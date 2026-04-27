import { useState, useEffect, useCallback } from "react";
import { Device, Site } from "@/api/entities";
import { apiFetch } from "@/api/client";
import {
  X, CheckCircle2, Radio, Pencil, Loader2, Link2, Unlink,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

/* ── Identity type helpers ── */
const STARLINK_MODELS = new Set(["napco-slelte", "napco-sle5g"]);
const ATA_MODELS = new Set(["cisco-ata191", "cisco-ata192"]);
const CARRIER_OPTIONS_DEV = ["T-Mobile", "Verizon", "AT&T", "Teal", "Napco", "Other"];

function identityTypeForModel(hwModelId) {
  if (STARLINK_MODELS.has(hwModelId)) return "starlink";
  if (ATA_MODELS.has(hwModelId)) return "ata";
  if (hwModelId) return "cellular";
  return "";
}

/* ── Carrier auto-detect from MSISDN prefix ── */
const CARRIER_PREFIXES = {
  "+1": [
    { prefix: "1310", carrier: "T-Mobile" }, { prefix: "1312", carrier: "T-Mobile" },
    { prefix: "1904", carrier: "T-Mobile" }, { prefix: "1786", carrier: "T-Mobile" },
  ],
};

function guessCarrier(msisdn) {
  const digits = msisdn.replace(/\D/g, "");
  if (digits.length >= 4) {
    for (const { prefix, carrier } of CARRIER_PREFIXES["+1"] || []) {
      if (digits.startsWith(prefix)) return carrier;
    }
  }
  return "";
}

const SIM_CARRIER_OPTIONS = ["Verizon", "T-Mobile", "AT&T", "Telnyx", "Teal", "Unknown"];

/* ── Assigned SIMs panel (shown inside edit modal) ── */
function DeviceSimPanel({ deviceId, deviceMsisdn }) {
  const { can } = useAuth();
  const [sims, setSims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [unassigning, setUnassigning] = useState(null);
  const [pickerMode, setPickerMode] = useState(null);
  const [availableSims, setAvailableSims] = useState([]);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [selectedSimId, setSelectedSimId] = useState("");
  const [manualMsisdn, setManualMsisdn] = useState("");
  const [manualIccid, setManualIccid] = useState("");
  const [manualCarrier, setManualCarrier] = useState("");

  const fetchSims = useCallback(async () => {
    try {
      const data = await apiFetch(`/devices/${deviceId}/sims`);
      setSims(data);
    } catch { /* silently fail */ }
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

  const handleOpenExisting = async () => {
    setPickerMode("existing");
    setPickerLoading(true);
    try {
      const data = await apiFetch("/sims?unassigned=true&limit=200");
      setAvailableSims(data);
    } catch {
      setAvailableSims([]);
    }
    setPickerLoading(false);
  };

  const handleOpenManual = () => {
    setPickerMode("manual");
    if (deviceMsisdn && !manualMsisdn) {
      setManualMsisdn(deviceMsisdn);
      setManualCarrier(guessCarrier(deviceMsisdn));
    }
  };

  const handleAssignExisting = async () => {
    if (!selectedSimId) return;
    setAssigning(true);
    try {
      await apiFetch(`/sims/${selectedSimId}/assign`, {
        method: "POST",
        body: JSON.stringify({ device_id: deviceId, slot: 1 }),
      });
      toast.success("SIM assigned to device");
      closePicker();
      fetchSims();
    } catch (err) {
      toast.error(err?.message || "Failed to assign SIM");
    }
    setAssigning(false);
  };

  const handleAssignManual = async () => {
    const msisdn = manualMsisdn.trim();
    if (!msisdn) {
      toast.error("MSISDN is required");
      return;
    }
    setAssigning(true);
    try {
      await apiFetch("/sims/assign-manual", {
        method: "POST",
        body: JSON.stringify({
          device_id: deviceId,
          msisdn,
          iccid: manualIccid.trim() || undefined,
          carrier: manualCarrier || "Unknown",
          slot: 1,
        }),
      });
      toast.success("SIM created and assigned");
      closePicker();
      fetchSims();
    } catch (err) {
      toast.error(err?.message || "Failed to assign SIM");
    }
    setAssigning(false);
  };

  const closePicker = () => {
    setPickerMode(null);
    setSelectedSimId("");
    setManualMsisdn("");
    setManualIccid("");
    setManualCarrier("");
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
            <div className="font-mono text-xs text-gray-700 truncate">
              {s.msisdn || s.iccid}
            </div>
            <div className="text-[10px] text-gray-500">
              {s.carrier}{s.iccid && !s.iccid.startsWith("MANUAL-") ? ` | ${s.iccid}` : ""} | {s.status}
              {s.data_source === "manual" && <span className="ml-1 text-blue-500">(manual)</span>}
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

      {sims.length === 0 && !pickerMode && (
        <div className="text-xs text-gray-400 py-1">No SIMs assigned to this device.</div>
      )}

      {can("MANAGE_SIMS") && !pickerMode && (
        <div className="flex gap-2 mt-1">
          <button
            onClick={handleOpenExisting}
            className="flex items-center gap-1.5 text-xs text-red-600 hover:text-red-700 font-medium"
          >
            <Link2 className="w-3 h-3" /> From Inventory
          </button>
          <button
            onClick={handleOpenManual}
            className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-700 font-medium"
          >
            <Pencil className="w-3 h-3" /> Enter Manually
          </button>
        </div>
      )}

      {pickerMode === "existing" && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 space-y-2">
          <div className="text-xs font-semibold text-gray-700">Select from Inventory</div>
          {pickerLoading ? (
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <Loader2 className="w-3 h-3 animate-spin" /> Loading available SIMs...
            </div>
          ) : availableSims.length === 0 ? (
            <div className="text-xs text-gray-400">
              No unassigned SIMs in inventory.
              <button onClick={handleOpenManual} className="ml-1 text-blue-600 underline font-medium">Enter manually instead</button>
            </div>
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
            <button onClick={closePicker} className="px-3 py-1.5 text-xs text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
            <button
              onClick={handleAssignExisting}
              disabled={!selectedSimId || assigning}
              className="px-3 py-1.5 text-xs text-white bg-red-600 hover:bg-red-700 disabled:bg-red-300 rounded-lg font-medium"
            >
              {assigning ? "Assigning..." : "Assign"}
            </button>
          </div>
        </div>
      )}

      {pickerMode === "manual" && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-2">
          <div className="text-xs font-semibold text-gray-700">Enter SIM Manually</div>
          {deviceMsisdn && manualMsisdn === deviceMsisdn && (
            <div className="text-[10px] text-blue-600 bg-blue-50 px-2 py-1 rounded">
              Pre-filled from device telemetry
            </div>
          )}
          <div>
            <label className="block text-[10px] text-gray-500 mb-0.5">MSISDN / Phone Number *</label>
            <input
              value={manualMsisdn}
              onChange={e => {
                setManualMsisdn(e.target.value);
                if (!manualCarrier) setManualCarrier(guessCarrier(e.target.value));
              }}
              placeholder="e.g. 19046890551"
              className="w-full px-3 py-1.5 border border-gray-300 rounded-lg text-xs font-mono focus:outline-none focus:ring-2 focus:ring-red-500"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[10px] text-gray-500 mb-0.5">ICCID (optional)</label>
              <input
                value={manualIccid}
                onChange={e => setManualIccid(e.target.value)}
                placeholder="SIM card number"
                className="w-full px-3 py-1.5 border border-gray-300 rounded-lg text-xs font-mono focus:outline-none focus:ring-2 focus:ring-red-500"
              />
            </div>
            <div>
              <label className="block text-[10px] text-gray-500 mb-0.5">Carrier</label>
              <select
                value={manualCarrier}
                onChange={e => setManualCarrier(e.target.value)}
                className="w-full px-3 py-1.5 border border-gray-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-red-500"
              >
                <option value="">-- Select --</option>
                {SIM_CARRIER_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={closePicker} className="px-3 py-1.5 text-xs text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
            <button
              onClick={handleAssignManual}
              disabled={!manualMsisdn.trim() || assigning}
              className="px-3 py-1.5 text-xs text-white bg-red-600 hover:bg-red-700 disabled:bg-red-300 rounded-lg font-medium"
            >
              {assigning ? "Assigning..." : "Create & Assign"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Device form modal — shared by Devices.jsx and SiteDetail.jsx.
 *
 * Props:
 *  - onClose, onSaved: required callbacks
 *  - sites, hardwareModels: lookup arrays
 *  - editDevice: optional record to enter edit mode
 *  - onSitesRefresh: optional callback to refresh sites after inline create
 *  - defaultSiteId: optional site_id to preselect on create
 *  - lockSite: when true, render the site selector read-only and hide the
 *    "+ New Site" inline create button.  Used when invoked from SiteDetail.
 */
export default function DeviceFormModal({
  onClose,
  onSaved,
  onSitesRefresh,
  sites,
  hardwareModels,
  editDevice,
  defaultSiteId,
  lockSite = false,
}) {
  const { can } = useAuth();
  const canEditStatus = can("DELETE_DEVICES");
  const isEdit = !!editDevice;
  const [form, setForm] = useState({
    device_id: editDevice?.device_id || "",
    imei: editDevice?.imei || "",
    iccid: editDevice?.iccid || "",
    msisdn: editDevice?.msisdn || "",
    carrier: editDevice?.carrier || "",
    site_id: editDevice?.site_id || defaultSiteId || "",
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

  const [showInlineSiteCreate, setShowInlineSiteCreate] = useState(false);
  const [inlineSite, setInlineSite] = useState({ site_name: "", e911_street: "", e911_city: "", e911_state: "", e911_zip: "" });
  const [inlineSiteCreating, setInlineSiteCreating] = useState(false);

  const handleInlineSiteCreate = async () => {
    if (!inlineSite.site_name.trim()) return;
    setInlineSiteCreating(true);
    try {
      const newSite = await Site.create({
        site_id: `SITE-${Date.now()}`,
        site_name: inlineSite.site_name.trim(),
        customer_name: inlineSite.site_name.trim(),
        status: "Not Connected",
        e911_street: inlineSite.e911_street.trim() || undefined,
        e911_city: inlineSite.e911_city.trim() || undefined,
        e911_state: inlineSite.e911_state.trim() || undefined,
        e911_zip: inlineSite.e911_zip.trim() || undefined,
      });
      onSitesRefresh?.();
      setForm(f => ({ ...f, site_id: newSite.site_id }));
      setShowInlineSiteCreate(false);
      setInlineSite({ site_name: "", e911_street: "", e911_city: "", e911_state: "", e911_zip: "" });
      toast.success(`Site "${newSite.site_name}" created`);
    } catch (err) {
      toast.error(err.message || "Failed to create site");
    } finally {
      setInlineSiteCreating(false);
    }
  };

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }));

  const idType = form.identifier_type || identityTypeForModel(form.hardware_model_id);
  const isCellular = idType === "cellular" || idType === "";
  const isStarlink = idType === "starlink";
  const isAta = idType === "ata";

  const mfrs = [...new Set(hardwareModels.map(m => m.manufacturer))].sort();

  const handleModelChange = (e) => {
    const id = e.target.value;
    if (id === "__custom") {
      setForm(f => ({ ...f, hardware_model_id: "__custom", model: "", manufacturer: "", device_type: "", identifier_type: "" }));
      return;
    }
    const hm = hardwareModels.find(m => m.id === id);
    const newIdType = identityTypeForModel(id);
    setForm(f => ({
      ...f,
      hardware_model_id: id,
      device_type: hm?.device_type || f.device_type,
      model: hm?.model_name || f.model,
      manufacturer: hm?.manufacturer || "",
      identifier_type: newIdType,
      ...(newIdType === "starlink" ? { imei: "", iccid: "", msisdn: "", carrier: "" } : {}),
      ...(newIdType === "ata" ? { imei: "", iccid: "", msisdn: "", carrier: "", starlink_id: "" } : {}),
      ...(newIdType === "cellular" ? { starlink_id: "" } : {}),
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (isStarlink && !form.starlink_id.trim()) {
      setError("StarLink ID is required for Napco devices.");
      return;
    }
    if (!isEdit && isCellular && !form.imei.trim() && !form.iccid.trim()) {
      setError("Cellular devices require at least one identifier: IMEI or SIM ICCID.");
      return;
    }
    if (!isEdit && isAta && !form.mac_address.trim()) {
      setError("IP-based devices require a MAC address.");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        device_id: form.device_id,
        site_id: form.site_id || undefined,
        hardware_model_id: (form.hardware_model_id && form.hardware_model_id !== "__custom") ? form.hardware_model_id : undefined,
        manufacturer: form.manufacturer || undefined,
        device_type: form.device_type || "Other",
        model: form.model || form.device_type,
        identifier_type: idType || undefined,
        serial_number: form.serial_number || undefined,
        mac_address: form.mac_address || undefined,
        notes: form.notes || undefined,
        ...(isCellular ? {
          imei: form.imei || undefined,
          iccid: form.iccid || undefined,
          msisdn: form.msisdn || undefined,
          carrier: form.carrier || undefined,
        } : {}),
        ...(isStarlink ? {
          starlink_id: form.starlink_id || undefined,
        } : {}),
      };

      if (isEdit) {
        const editPayload = canEditStatus
          ? { ...payload, status: form.status }
          : payload;
        await Device.update(editDevice.id, editPayload);
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

  const lockedSite = lockSite && form.site_id
    ? sites.find(s => s.site_id === form.site_id)
    : null;

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
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Internal Device ID *</label>
            <input
              value={form.device_id}
              onChange={set("device_id")}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent font-mono"
              placeholder="e.g. RH-DAL-ELEV-01"
              required
              disabled={isEdit}
            />
            <p className="mt-1 text-xs text-gray-500">
              Used by True911 for internal tracking. Suggested pattern <span className="font-mono text-gray-600">CUSTOMER-SITE-ENDPOINT-##</span> — e.g. <span className="font-mono text-gray-600">RH-DAL-ELEV-01</span>, <span className="font-mono text-gray-600">BEN-STJ-FACP-01</span>, <span className="font-mono text-gray-600">RRR-DSM-CALL-01</span>.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Hardware Model</label>
            <select
              value={form.hardware_model_id}
              onChange={handleModelChange}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
            >
              <option value="">-- Select from catalog --</option>
              {mfrs.map(mfr => (
                <optgroup key={mfr} label={mfr}>
                  {hardwareModels.filter(m => m.manufacturer === mfr).map(m => (
                    <option key={m.id} value={m.id}>{m.model_name}</option>
                  ))}
                </optgroup>
              ))}
              <optgroup label="Other">
                <option value="__custom">Enter custom manufacturer / model</option>
              </optgroup>
            </select>
          </div>
          {form.hardware_model_id === "__custom" && (
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Custom Model Name *</label>
              <input
                value={form.model}
                onChange={set("model")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="e.g. Acme Router X100"
                required
              />
            </div>
          )}
          {form.hardware_model_id === "__custom" && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Manufacturer</label>
                <input
                  value={form.manufacturer || ""}
                  onChange={e => setForm(f => ({ ...f, manufacturer: e.target.value }))}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                  placeholder="e.g. FlyingVoice, Napco, Cisco"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Device Type</label>
                <select
                  value={form.device_type}
                  onChange={set("device_type")}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                >
                  <option value="">Select...</option>
                  <option value="cellular">Cellular Router / Communicator</option>
                  <option value="ata">ATA / Analog Adapter</option>
                  <option value="starlink">Napco StarLink Panel</option>
                  <option value="other">Other</option>
                </select>
              </div>
            </div>
          )}

          {idType && (
            <div className="text-xs text-gray-600 bg-gray-50 border border-gray-100 px-3 py-2 rounded-lg">
              {isStarlink && (
                <>
                  <span className="font-semibold text-gray-700">Napco StarLink device.</span>{" "}
                  Internal Device ID is your True911 tracking name; Napco Panel ID is the manufacturer identifier. No MAC or IMEI required.
                </>
              )}
              {isCellular && "Cellular device — at least one of IMEI or SIM ICCID is required. MAC is optional."}
              {isAta && "IP-based device — MAC address is required."}
            </div>
          )}

          {isCellular && (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">IMEI {!isEdit && <span className="text-gray-400 normal-case">(or ICCID)</span>}</label>
                  <input
                    value={form.imei}
                    onChange={set("imei")}
                    className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                    placeholder="15-digit IMEI"
                    maxLength={15}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">SIM ICCID {!isEdit && <span className="text-gray-400 normal-case">(or IMEI)</span>}</label>
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

          {isStarlink && (
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Napco Panel ID / StarLink ID *</label>
              <input
                value={form.starlink_id}
                onChange={set("starlink_id")}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent font-mono"
                placeholder="Napco Panel ID"
                required
              />
              <p className="mt-1 text-xs text-gray-500">
                Required for Napco StarLink devices. This is the manufacturer / network identifier — not your internal Device ID.
              </p>
            </div>
          )}

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
            {!isStarlink && (
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">
                  MAC Address {isAta ? "*" : <span className="text-gray-400 normal-case">(optional)</span>}
                </label>
                <input
                  value={form.mac_address}
                  onChange={set("mac_address")}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                  placeholder="AA:BB:CC:DD:EE:FF"
                  maxLength={17}
                  required={isAta && !isEdit}
                />
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Assign to Site</label>
            {lockSite ? (
              <input
                value={lockedSite ? lockedSite.site_name : form.site_id || ""}
                disabled
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 text-gray-500"
              />
            ) : (
              <div className="flex gap-2">
                <select
                  value={form.site_id}
                  onChange={set("site_id")}
                  className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                >
                  <option value="">-- Select site --</option>
                  {sites.map(s => (
                    <option key={s.site_id} value={s.site_id}>{s.site_name}</option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => setShowInlineSiteCreate(true)}
                  className="px-3 py-2.5 border border-gray-300 rounded-xl text-xs font-semibold text-red-600 hover:bg-red-50 transition-colors whitespace-nowrap"
                >
                  + New Site
                </button>
              </div>
            )}
          </div>

          {!lockSite && showInlineSiteCreate && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-blue-900 uppercase tracking-wide">Quick Add Site</span>
                <button type="button" onClick={() => setShowInlineSiteCreate(false)} className="text-blue-400 hover:text-blue-600"><X className="w-3.5 h-3.5" /></button>
              </div>
              <input value={inlineSite.site_name} onChange={e => setInlineSite(s => ({...s, site_name: e.target.value}))}
                className="w-full px-3 py-2 border border-blue-200 rounded-lg text-sm" placeholder="Site name *" />
              <input value={inlineSite.e911_street} onChange={e => setInlineSite(s => ({...s, e911_street: e.target.value}))}
                className="w-full px-3 py-2 border border-blue-200 rounded-lg text-sm" placeholder="Street address" />
              <div className="grid grid-cols-3 gap-2">
                <input value={inlineSite.e911_city} onChange={e => setInlineSite(s => ({...s, e911_city: e.target.value}))}
                  className="px-3 py-2 border border-blue-200 rounded-lg text-sm" placeholder="City" />
                <input value={inlineSite.e911_state} onChange={e => setInlineSite(s => ({...s, e911_state: e.target.value}))}
                  className="px-3 py-2 border border-blue-200 rounded-lg text-sm" placeholder="State" maxLength={2} />
                <input value={inlineSite.e911_zip} onChange={e => setInlineSite(s => ({...s, e911_zip: e.target.value}))}
                  className="px-3 py-2 border border-blue-200 rounded-lg text-sm" placeholder="ZIP" maxLength={10} />
              </div>
              <button type="button" onClick={handleInlineSiteCreate} disabled={inlineSiteCreating || !inlineSite.site_name.trim()}
                className="w-full py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-xs font-semibold">
                {inlineSiteCreating ? "Creating..." : "Create & Select Site"}
              </button>
            </div>
          )}

          {isEdit && canEditStatus && (
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

          {isEdit && (
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">
                <span className="flex items-center gap-1"><Link2 className="w-3 h-3" /> Assigned SIMs</span>
              </label>
              <DeviceSimPanel deviceId={editDevice.id} deviceMsisdn={editDevice.msisdn} />
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
